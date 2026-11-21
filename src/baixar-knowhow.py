#!/usr/bin/env python3
"""
Baixar KnowHow - Extrator de Sabedoria
Extrai transcricoes de videos (YouTube) e compila em MD
com resumo de temas, assuntos e know-how do canal.

Uso:
    python baixar-knowhow.py <URL da playlist/canal/video>
    python baixar-knowhow.py arquivo.txt  (um link por linha)

O que faz:
    1. Extrai transcricao via YouTube (legendas nativas ou automaticas)
    2. Se nao houver legendas, faz transcricao local com faster-whisper
    3. Salva cada transcricao em TXT cru (pasta transcricoes/)
    4. Compila em MD por canal/playlist com resumo e temas (pasta knowhow/)
"""

import sys
import os

# Configura encoding UTF-8 para stdout no Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import yt_dlp
import json
import re
import time
import glob
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict
import urllib.parse as urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# ── caminhos ──────────────────────────────────────────────────────────────
RAIZ = Path(__file__).parent
TRANSCRICOES = RAIZ / "transcricoes"       # transcrições brutas (.txt)
KNOWHOW = RAIZ / "knowhow"                   # compilados em markdown (.md)
APOSTILAS = RAIZ / "apostilas"               # apostilas e playbooks (.md)
COOKIES_FILE = RAIZ / "cookies.txt"

# ── configs ───────────────────────────────────────────────────────────────
IDIOMAS_PREFERIDOS = ["pt", "pt-BR", "pt-PT", "en", "es", "fr"]
WHISPER_MODELO = "base"  # tiny, base, small, medium, large-v3
DENO_PATH = None

# Tenta achar o deno
for candidato in [
    r"C:\Users\r4ryz\AppData\Local\Programs\Python\Python312\deno\deno.exe",
    "deno", "deno.exe",
]:
    try:
        import subprocess
        subprocess.run([candidato, "--version"], capture_output=True, timeout=5, shell=True)
        DENO_PATH = candidato
        break
    except Exception:
        continue


def log(msg, tipo="INFO"):
    """Log simples com timestamp."""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{tipo}] {msg}")


# ══════════════════════════════════════════════════════════════════════════
#  1. EXTRAÇÃO DE METADADOS E LISTA DE VÍDEOS
# ══════════════════════════════════════════════════════════════════════════

def extrair_info(url):
    """Extrai metadados de uma URL (pode ser vídeo, playlist ou canal)."""
    opts_base = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
    }
    if DENO_PATH:
        opts_base["js_runtimes"] = {"deno": {"path": DENO_PATH}}
    if COOKIES_FILE.exists():
        opts_base["cookiefile"] = str(COOKIES_FILE)

    # Primeira tentativa: com extract_flat (mais rápido)
    opts = {**opts_base, "extract_flat": "in_playlist"}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    # Se é um canal/playlist com 0 entradas, tenta formatos alternativos
    if info and info.get("_type") == "playlist" and not info.get("entries"):
        channel_id = info.get("channel_id") or info.get("id")
        uploader = info.get("uploader", "")

        # Lista de formatos a tentar
        formatos_tentar = []
        if channel_id:
            formatos_tentar.append(f"https://www.youtube.com/channel/{channel_id}/videos")
        if uploader:
            formatos_tentar.append(f"https://www.youtube.com/@{uploader}/videos")

        # Tenta o formato de playlist de uploads (mais confiável)
        if channel_id:
            formatos_tentar.append(
                f"https://www.youtube.com/playlist?list=UU{channel_id[2:]}"
            )

        for fmt_url in formatos_tentar:
            try:
                log(f"Tentando formato alternativo: {fmt_url}")
                with yt_dlp.YoutubeDL(opts) as ydl2:
                    info2 = ydl2.extract_info(fmt_url, download=False)
                if info2 and info2.get("entries"):
                    entries = [e for e in info2.get("entries", []) if e]
                    if entries:
                        log(f"Formato {fmt_url} retornou {len(entries)} videos")
                        return info2
            except Exception as e:
                log(f"  -> formato falhou: {str(e)[:80]}", "AVISO")
                continue

        # Se ainda não achou, tenta puxar sem extract_flat (mais pesado, mas pode funcionar)
        log("Tentando extracao detalhada (sem extract_flat)...")
        try:
            opts_pesado = {**opts_base, "extract_flat": False, "playlistend": 50}
            with yt_dlp.YoutubeDL(opts_pesado) as ydl3:
                info3 = ydl3.extract_info(url, download=False)
            if info3 and info3.get("entries"):
                entries = [e for e in info3.get("entries", []) if e]
                if entries:
                    log(f"Extracao detalhada retornou {len(entries)} videos")
                    return info3
        except Exception as e:
            log(f"  -> extracao detalhada falhou: {str(e)[:80]}", "AVISO")

    return info


def listar_videos(info):
    """
    Retorna lista de dicts com id, title, url de cada vídeo.
    Lida com: vídeo único, playlist, canal (via uploads).
    """
    videos = []
    _extrair_videos(info, videos)
    return videos


def listar_videos_da_pasta():
    """
    Escaneia a pasta baixados/ e extrai metadados dos MP4s já baixados.
    Útil quando o YouTube não libera a lista de vídeos do canal.
    """
    pasta = RAIZ / "baixados"
    if not pasta.exists():
        return []

    videos = []
    for f in sorted(pasta.iterdir()):
        if f.suffix.lower() in (".mp4", ".mkv", ".webm", ".m4a"):
            nome = f.stem  # nome sem extensão
            # Tenta extrair info com yt-dlp
            try:
                opts = {"quiet": True, "no_warnings": True, "ignoreerrors": True}
                if DENO_PATH:
                    opts["js_runtimes"] = {"deno": {"path": DENO_PATH}}
                with yt_dlp.YoutubeDL(opts) as ydl:
                    # Busca pelo titulo pra achar o video
                    info = ydl.extract_info(f"ytsearch:{nome}", download=False)
                    entries = info.get("entries") or []
                    if entries and entries[0]:
                        e = entries[0]
                        videos.append({
                            "id": e.get("id", ""),
                            "title": e.get("title", nome),
                            "url": f"https://www.youtube.com/watch?v={e.get('id', '')}",
                            "duration": e.get("duration", 0),
                            "upload_date": e.get("upload_date", ""),
                            "channel": e.get("channel", e.get("uploader", "Desconhecido")),
                            "channel_url": e.get("channel_url", ""),
                            "description": e.get("description", ""),
                            "playlist": "",
                            "_arquivo_local": str(f),
                            "_fonte": "pasta_baixados",
                        })
                        continue
            except Exception:
                pass

            # Fallback: usa só o nome do arquivo
            videos.append({
                "id": "",
                "title": nome,
                "url": "",
                "duration": 0,
                "upload_date": "",
                "channel": "Desconhecido",
                "channel_url": "",
                "description": "",
                "playlist": "",
                "_arquivo_local": str(f),
                "_fonte": "pasta_baixados",
            })

    return videos


def _extrair_videos(entry, resultado):
    """Percorre recursivamente extraindo entradas de vídeo."""
    if entry is None:
        return

    # Detecta se é uma entrada do tipo "url" (extract_flat retorna isso)
    if entry.get("_type") == "url" and entry.get("id") and entry.get("title"):
        vid = {
            "id": entry["id"],
            "title": entry.get("title", "Sem título"),
            "url": entry.get("url", f"https://www.youtube.com/watch?v={entry['id']}"),
            "duration": entry.get("duration", 0),
            "upload_date": entry.get("upload_date", ""),
            "channel": entry.get("channel", entry.get("uploader", "")),
            "channel_url": entry.get("channel_url", entry.get("uploader_url", "")),
            "description": entry.get("description", ""),
            "playlist": entry.get("playlist_title", ""),
        }
        if vid["id"] and vid not in resultado:
            resultado.append(vid)
        return

    # Detecta se é uma entrada flat (dict simples de extract_flat sem _type)
    if ("id" in entry and "title" in entry
        and not entry.get("_type")
        and not entry.get("entries")):
        vid = {
            "id": entry["id"],
            "title": entry.get("title", "Sem título"),
            "url": f"https://www.youtube.com/watch?v={entry['id']}",
            "duration": entry.get("duration", 0),
            "upload_date": entry.get("upload_date", ""),
            "channel": entry.get("channel", entry.get("uploader", "")),
            "channel_url": entry.get("channel_url", entry.get("uploader_url", "")),
            "description": entry.get("description", ""),
            "playlist": entry.get("playlist_title", ""),
        }
        if vid["id"] and vid not in resultado:
            resultado.append(vid)
        return

    # É um único vídeo (formato completo)
    if entry.get("_type") == "video":
        _extrair_videos(entry, resultado)
        return

    # Playlist / canal / mixed
    if "_type" in entry:
        if entry["_type"] in ("playlist", "multi", "compat_list"):
            entries = entry.get("entries") or []
            for e in entries:
                if e is None:
                    continue
                _extrair_videos(e, resultado)

    # Tenta entries mesmo sem _type
    entries = entry.get("entries") or []
    for e in entries:
        if e is None:
            continue
        _extrair_videos(e, resultado)


# ══════════════════════════════════════════════════════════════════════════
#  2. EXTRAÇÃO DE TRANSCRIÇÃO (LEGENDAS)
# ══════════════════════════════════════════════════════════════════════════

def baixar_legendas(video_info):
    """
    Tenta baixar legendas do YouTube (nativas ou automáticas).
    Retorna (texto_bruto, idioma) ou (None, None).
    """
    video_id = video_info.get("id", "")
    if not video_id:
        return None, None

    url = video_info.get("url", "")

    opts = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitlesformat": "vtt",
        "subtitleslangs": IDIOMAS_PREFERIDOS,
        "outtmpl": str(RAIZ / "tmp_subs" / f"{video_id}.%(ext)s"),
        "convert_subs": "srt",  # VTT -> SRT é mais fácil de parsear
    }
    if DENO_PATH:
        opts["js_runtimes"] = {"deno": {"path": DENO_PATH}}
    if COOKIES_FILE.exists():
        opts["cookiefile"] = str(COOKIES_FILE)

    tmp_dir = RAIZ / "tmp_subs"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            # Extrai info primeiro para ver legendas disponíveis
            info = ydl.extract_info(url, download=False)

        # Descobre legendas disponíveis
        subtitles = info.get("subtitles") or {}
        automatic_captions = info.get("automatic_captions") or {}

        lingua = _melhor_idioma(subtitles, automatic_captions)
        if not lingua:
            log(f"Sem legendas disponíveis para {video_id}", "AVISO")
            limpar_tmp(tmp_dir)
            return None, None

        log(f"Legendas encontradas: {lingua} para {video_id}")

        # Baixa de fato
        opts["subtitleslangs"] = [lingua]
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

        # Encontra o arquivo baixado
        srt_files = list(tmp_dir.glob(f"{video_id}*.srt"))
        vtt_files = list(tmp_dir.glob(f"{video_id}*.vtt"))

        arquivo = None
        for f in srt_files + vtt_files:
            if lingua in f.name or not arquivo:
                arquivo = f
                break
        if not arquivo and (srt_files or vtt_files):
            arquivo = (srt_files or vtt_files)[0]

        if arquivo and arquivo.exists():
            texto = parsear_legenda(arquivo)
            limpar_tmp(tmp_dir)
            return texto, lingua

        limpar_tmp(tmp_dir)
        return None, None

    except Exception as e:
        log(f"Erro ao baixar legendas de {video_id}: {e}", "ERRO")
        limpar_tmp(tmp_dir)
        return None, None


def _melhor_idioma(subtitles, auto_captions):
    """Escolhe o melhor idioma disponível entre legendas nativas e automáticas."""
    # Junta tudo
    todos = {}
    for key in set(list(subtitles.keys()) + list(auto_captions.keys())):
        entry = subtitles.get(key) or auto_captions.get(key) or []
        # Verifica se tem pelo menos um formato com URL
        tem_url = any(
            isinstance(f, dict) and f.get("url") for f in entry
        )
        if tem_url:
            todos[key] = True

    if not todos:
        return None

    # Preferência de idiomas
    for lang in IDIOMAS_PREFERIDOS:
        if lang in todos:
            return lang
        # Fallback: pt-BR -> pt
        base = lang.split("-")[0]
        for k in todos:
            if k.startswith(base):
                return k

    # Qualquer um disponível
    return list(todos.keys())[0]


def parsear_legenda(caminho):
    """
    Parseia arquivo .srt ou .vtt e retorna texto limpo.
    Remove timestamps, tags HTML, numerações.
    """
    raw = caminho.read_text(encoding="utf-8", errors="replace")

    # Remove tags HTML
    raw = re.sub(r"<[^>]+>", "", raw)

    linhas = raw.split("\n")
    texto = []
    for linha in linhas:
        linha = linha.strip()
        # Pula linhas de timestamp (contém -->)
        if "-->" in linha:
            continue
        # Pula numeração de SRT
        if linha.isdigit():
            continue
        # Pula cabeçalhos VTT
        if linha.lower().startswith("webvtt") or linha.startswith("Kind:") or linha.startswith("Language:"):
            continue
        # Pula linhas vazias
        if not linha:
            continue
        texto.append(linha)

    return "\n".join(texto)


# ══════════════════════════════════════════════════════════════════════════
#  3. TRANSCRIÇÃO LOCAL COM FASTER-WHISPER (FALLBACK)
# ══════════════════════════════════════════════════════════════════════════

def transcrever_local(video_info):
    """
    Baixa o audio e transcreve localmente com faster-whisper.
    Se o video_info tiver '_arquivo_local', usa o arquivo ja baixado.
    Retorna (texto_transcricao, "pt") ou (None, None).
    """
    video_id = video_info.get("id", "") or "desconhecido"
    if not video_id or video_id == "desconhecido":
        video_id = "desconhecido"
    arquivo_local = video_info.get("_arquivo_local")
    caminho_audio = None
    precisa_limpar = False

    if arquivo_local and os.path.isfile(arquivo_local):
        log(f"Usando arquivo local: {Path(arquivo_local).name}")
        caminho_audio = arquivo_local
    else:
        opts_audio = {
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
            "format": "bestaudio[ext=m4a]/bestaudio",
            "outtmpl": str(RAIZ / "tmp_audio" / f"{video_id}.%(ext)s"),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
            }],
            "prefer_ffmpeg": True,
        }
        if DENO_PATH:
            opts_audio["js_runtimes"] = {"deno": {"path": DENO_PATH}}
        if COOKIES_FILE.exists():
            opts_audio["cookiefile"] = str(COOKIES_FILE)

        tmp_audio = RAIZ / "tmp_audio"
        tmp_audio.mkdir(parents=True, exist_ok=True)
        precisa_limpar = True

        try:
            log(f"Baixando audio de {video_id} para transcricao local...")
            with yt_dlp.YoutubeDL(opts_audio) as ydl:
                ydl.download([video_info["url"]])

            wavs = list(tmp_audio.glob(f"{video_id}*.wav"))
            if not wavs:
                m4as = list(tmp_audio.glob(f"{video_id}*.m4a"))
                if m4as:
                    wavs = m4as
            if not wavs:
                log(f"Audio nao encontrado para {video_id}", "ERRO")
                limpar_tmp(tmp_audio)
                return None, None

            caminho_audio = str(wavs[0])
        except Exception as e:
            log(f"Erro baixando audio de {video_id}: {e}", "ERRO")
            limpar_tmp(tmp_audio)
            return None, None

    # --- Transcricao ---
    if not caminho_audio:
        return None, None

    log(f"Transcrevendo com faster-whisper ({WHISPER_MODELO})...")

    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(WHISPER_MODELO, device="cpu", compute_type="int8")
        segments, info = model.transcribe(caminho_audio, beam_size=5)
        texto = "\n".join(seg.text for seg in segments)
        log(f"Transcricao concluida: {len(texto)} caracteres")
        if precisa_limpar:
            limpar_tmp(tmp_audio)
        return texto, "pt"
    except ImportError:
        log("faster-whisper nao disponivel, tentando openai-whisper...", "AVISO")
    except Exception as e:
        log(f"Erro na transcricao com faster-whisper: {e}", "ERRO")

    # Fallback para openai-whisper
    try:
        import whisper
        model = whisper.load_model(WHISPER_MODELO)
        result = model.transcribe(caminho_audio)
        texto = result["text"]
        if precisa_limpar:
            limpar_tmp(tmp_audio)
        return texto, "pt"
    except ImportError:
        log("Nenhum engine de transcricao local disponivel!", "ERRO")
    except Exception as e:
        log(f"Erro na transcricao com openai-whisper: {e}", "ERRO")

    if precisa_limpar:
        limpar_tmp(tmp_audio)
    return None, None


def limpar_tmp(pasta):
    """Remove arquivos temporários."""
    if pasta.exists():
        for f in pasta.iterdir():
            try:
                f.unlink()
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════
#  4. SALVAR TRANSCRIÇÕES INDIVIDUAIS
# ══════════════════════════════════════════════════════════════════════════

def nome_arquivo_seguro(titulo, max_len=80):
    """Remove caracteres inválidos para nome de arquivo."""
    nome = re.sub(r'[<>:"/\\|?*]', "_", titulo)
    nome = re.sub(r"\s+", " ", nome).strip()
    if len(nome) > max_len:
        nome = nome[:max_len].rstrip()
    return nome


def salvar_transcricao(video_info, texto, idioma):
    """Salva transcrição em TXT."""
    TRANSCRICOES.mkdir(parents=True, exist_ok=True)
    nome_base = nome_arquivo_seguro(video_info.get("title", "video"))
    canal = nome_arquivo_seguro(video_info.get("channel", "desconhecido"), 40)
    pasta_canal = TRANSCRICOES / canal
    pasta_canal.mkdir(parents=True, exist_ok=True)

    video_id = video_info.get("id", video_info.get("_arquivo_local", ""))
    if not video_id:
        import hashlib
        video_id = hashlib.md5(nome_base.encode()).hexdigest()[:8]

    arquivo = pasta_canal / f"{nome_base}__{video_id}.txt"

    cabecalho = f"""╔══════════════════════════════════════════════╗
║  TRANSCRIÇÃO — {video_info.get('title', '?')}
║  Canal: {video_info.get('channel', '?')}
║  ID: {video_id}
║  Idioma: {idioma or 'N/A'}
║  Data extração: {datetime.now().strftime('%d/%m/%Y %H:%M')}
╚══════════════════════════════════════════════╝

"""
    with open(arquivo, "w", encoding="utf-8") as f:
        f.write(cabecalho)
        f.write(texto if texto else "[TRANSCRIÇÃO NÃO DISPONÍVEL]")

    log(f"Transcrição salva: {arquivo.name}")
    return arquivo


# ══════════════════════════════════════════════════════════════════════════
#  5. COMPILAÇÃO EM MARKDOWN — KNOWHOW
# ══════════════════════════════════════════════════════════════════════════

def analisar_temas(textos_dos_videos):
    """
    Análise simples de palavras-chave para extrair temas.
    Retorna um dict com contagem de termos relevantes.
    """
    # Palavras/padrões de interesse (conhecimento financeiro/investimentos + trading)
    PADRÕES_TEMAS = [
        (r"(?i)\bbitcoin\b", "Bitcoin / Criptomoedas"),
        (r"(?i)\bcripto[a-zà-ú]*\b", "Criptomoedas"),
        (r"(?i)\bimóvel\w*\b|\bimovel\b", "Imóveis"),
        (r"(?i)\binvestir\b|\binvestimento\b", "Investimentos"),
        (r"(?i)\bpatrimônio\b|\bpatrimonio\b|\bpatrimonial\b", "Patrimônio"),
        (r"(?i)\bd[víi]vida\b|\bendividamento\b", "Dívidas"),
        (r"(?i)\brenda\s+passiva\b", "Renda Passiva"),
        (r"(?i)\baluguel\b|\balugar\b", "Aluguel"),
        (r"(?i)\bd[óo]lar\b", "Dólar / Câmbio"),
        (r"(?i)\briqueza\b|\brico\b|\bricos?\b", "Riqueza"),
        (r"(?i)\bfgts\b", "FGTS"),
        (r"(?i)\bdefi\b", "DeFi"),
        (r"(?i)\bativo\w*\s+no\s+exterior\b", "Ativos no Exterior"),
        (r"(?i)\ba[cççõ]ões?\b|\bacao\b|\ba[cç]ao\b", "Ações / Bolsa"),
        (r"(?i)\bfinan[cç]as?\b|\bfinanceir[oa]\b", "Finanças"),
        (r"(?i)\bpoupan[cç]a\b", "Poupança"),
        (r"(?i)\bjuros?\b", "Juros"),
        (r"(?i)\binfla[cççã]ão\b", "Inflação"),
        (r"(?i)\bimposto\w*\b|\btributa[cçã]ão\b", "Impostos"),
        (r"(?i)\baposentadoria\b", "Aposentadoria"),
        (r"(?i)\brisco\b|\briscos?\b", "Risco"),
        (r"(?i)\bliquidez\b", "Liquidez"),
        (r"(?i)\bdiversif[a-zà-ú]*\b", "Diversificação"),
        (r"(?i)\bmercado\s+financeiro\b", "Mercado Financeiro"),
        (r"(?i)\bbilion[áa]rio\w*\b", "Bilionários"),
        (r"(?i)\bobriga[cçõ]ões?\b", "Obrigações"),
        # Temas de trading / sistemas
        (r"(?i)\btrading\b|\btrader\b", "Trading"),
        (r"(?i)\bdesvio\s+padrão\b|\bdesvio\s+padrao\b", "Desvio Padrão"),
        (r"(?i)\bfluxo\s+de\s+ordens\b", "Fluxo de Ordens"),
        (r"(?i)\bdelta\s+flow\b|\bdeltaflow\b", "Delta Flow"),
        (r"(?i)\bgerenciamento\b", "Gerenciamento"),
        (r"(?i)\bcurva\s+de\s+gauss\b|\bgauss\b", "Curva de Gauss"),
        (r"(?i)\brobo\b|\bbot\b|\bdelta\b", "Robôs / Automação"),
        (r"(?i)\bestrat[ée]gia\w*\b|\bestrategic\w*\b", "Estratégia"),
        (r"(?i)\bforex\b|\bfx\b", "Forex"),
        (r"(?i)\bopera[cçã]ão\w*\b|\boperacional\b", "Operacional"),
        (r"(?i)\bsetup\w*\b|\bconfigura[cçã]ão\b", "Setups / Configuração"),
        (r"(?i)\ban[áa]lise\b|\banalisar\b", "Análise"),
        (r"(?i)\bobserva[cçã]ão\b|\bobservar\b", "Observação"),
        # Temas gerais
        (r"(?i)\btecnologia\b|\bt[ée]cnico\b", "Tecnologia"),
        (r"(?i)\bconhecimento\b|\bsabedoria\b", "Conhecimento"),
        (r"(?i)\baprender\b|\bestudo\b|\bestudar\b", "Aprendizado"),
        (r"(?i)\bsistema\b", "Sistemas"),
        (r"(?i)\bmetodologia\b|\bm[ée]todo\b", "Metodologia"),
    ]

    contagem = Counter()
    for texto in textos_dos_videos:
        if not texto:
            continue
        for padrao, tema in PADRÕES_TEMAS:
            ocorrencias = re.findall(padrao, texto)
            if ocorrencias:
                contagem[tema] += len(ocorrencias)

    return contagem


def compilar_knowhow(info_canal, videos_info, transcricoes_texto, erros):
    """
    Gera o arquivo markdown compilado com:
    - Metadados do canal
    - Resumo geral
    - Temas e assuntos recorrentes
    - Lista de vídeos processados
    - Transcrições limpas de cada vídeo
    """
    KNOWHOW.mkdir(parents=True, exist_ok=True)

    canal_nome = info_canal.get("channel") or info_canal.get("uploader") or "Canal Desconhecido"
    playlist_nome = info_canal.get("playlist_title") or ""
    titulo = info_canal.get("title") or ""

    # Nome do arquivo
    nome_base = nome_arquivo_seguro(canal_nome, 50)
    if playlist_nome:
        nome_base += f"__{nome_arquivo_seguro(playlist_nome, 40)}"

    md_path = KNOWHOW / f"{nome_base}.md"

    # Análise de temas
    textos_validos = [t for t in transcricoes_texto if t]
    temas = analisar_temas(textos_validos)

    # Vídeos que deram certo
    videos_ok = [(v, t) for v, t in zip(videos_info, transcricoes_texto) if t]

    with open(md_path, "w", encoding="utf-8") as md:
        md.write(f"""# 📚 KnowHow Extraído

**Canal:** {canal_nome}
""")
        if playlist_nome:
            md.write(f"**Playlist:** {playlist_nome}\n")
        if titulo and titulo != playlist_nome:
            md.write(f"**Título:** {titulo}\n")

        md.write(f"""**Data da extração:** {datetime.now().strftime('%d/%m/%Y %H:%M')}
**Total de vídeos processados:** {len(videos_info)}
**Vídeos com transcrição:** {len(videos_ok)}
**Vídeos sem transcrição:** {len(erros)}

---

## 📊 Temas e Assuntos Recorrentes

| Tema | Menções |
|------|---------|
""")

        for tema, count in temas.most_common(20):
            md.write(f"| {tema} | {count} |\n")

        md.write(f"""
---

## 📝 Resumo do Conhecimento do Canal

Este documento compila as transcrições de **{len(videos_ok)} vídeos** do canal **{canal_nome}**.
Os principais temas abordados são:

""")

        if temas:
            for tema, count in temas.most_common(10):
                md.write(f"- **{tema}** — mencionado {count} vezes\n")
        else:
            md.write("- *(Nenhum tema específico identificado)*\n")

        # Gera um resumo concatenando os primeiros X caracteres de cada vídeo
        md.write(f"""
---

## 🎬 Vídeos Processados

| # | Título | Duração | Data | Transcrição |
|---|--------|---------|------|-------------|
""")

        for i, (v, t) in enumerate(videos_ok, 1):
            dur = v.get("duration", 0)
            dur_str = f"{dur//60:02d}:{dur%60:02d}" if dur else "?"
            data = v.get("upload_date", "")
            if data and len(data) == 8:
                data_str = f"{data[6:8]}/{data[4:6]}/{data[:4]}"
            else:
                data_str = "?"
            status = "✅" if t else "❌"
            md.write(f"| {i} | {v['title']} | {dur_str} | {data_str} | {status} |\n")

        md.write(f"""
---

## 📖 Transcrições Completas

""")

        for i, (v, texto) in enumerate(videos_ok, 1):
            titulo_clean = v["title"].replace("|", "-")
            md.write(f"""
---

### 🎬 {i}. {titulo_clean}

**Link:** [{v['id']}]({v['url']})  
**Duração:** {f'{v["duration"]//60:02d}:{v["duration"]%60:02d}' if v.get('duration') else '?'}  
**Publicado:** {data_str if (data_str := v.get('upload_date','')) and len(data_str)==8 else '?'}

```
{texto[:3000]}{'...' if len(texto) > 3000 else ''}
```

""")

        # Adiciona seções com texto completo cortado
        if erros:
            md.write(f"""
---

## ⚠️ Vídeos sem Transcrição

Os seguintes vídeos não tiveram transcrição disponível:

""")
            for e in erros:
                md.write(f"- [{e['title']}]({e['url']}) — {e.get('motivo', 'desconhecido')}\n")

        # Informações sobre onde estão os TXT separados
        md.write(f"""
---

## 📁 Arquivos Individuais

As transcrições brutas de cada vídeo estão disponíveis em arquivos `.txt` na pasta `transcricoes/{nome_arquivo_seguro(canal_nome, 40)}/`.

---

*Documento gerado automaticamente por **Baixar KnowHow** em {datetime.now().strftime('%d/%m/%Y às %H:%M')}.*
""")

    log(f"KnowHow compilado: {md_path.name}")
    return md_path


# ══════════════════════════════════════════════════════════════════════════
#  6. GERACAO DE APOSTILAS E PLAYBOOKS
# ══════════════════════════════════════════════════════════════════════════

def _extrair_frases_chave(texto, tema, max_frases=5):
    """Extrai frases relevantes sobre um tema de um texto."""
    if not texto:
        return []
    frases = []
    for linha in texto.split("\n"):
        linha = linha.strip()
        if not linha or len(linha) < 20:
            continue
        if re.search(rf"(?i)\b{tema[:20]}\b", linha):
            # Limpa e encurta
            frases.append(linha[:200])
            if len(frases) >= max_frases:
                break
    return frases


def _resumir_topico(tema, textos):
    """Gera um resumo textual de um tema a partir das transcricoes."""
    fragmentos = []
    for t in textos:
        if not t:
            continue
        # Pega paragrafos que mencionam o tema
        for paragrafo in t.split("\n"):
            p = paragrafo.strip()
            if not p or len(p) < 30:
                continue
            palavras_tema = tema.lower().split()[:3]
            if any(palavra in p.lower() for palavra in palavras_tema):
                fragmentos.append(p[:300])
    return fragmentos[:8]


def gerar_apostila(info_canal, videos_info, transcricoes_texto, erros):
    """
    Gera uma APOSTILA (livro de estudo) em MD com:
    - Conhecimento adquirido
    - Conteudo abordado
    - Jornada de aprendizado
    - Capitulos por tema
    - Resumo executivo
    """
    APOSTILAS.mkdir(parents=True, exist_ok=True)

    canal_nome = info_canal.get("channel") or info_canal.get("uploader") or "Canal Desconhecido"
    playlist_nome = info_canal.get("playlist_title") or ""

    nome_base = nome_arquivo_seguro(canal_nome, 50)
    pasta_apostila = APOSTILAS / nome_base
    pasta_apostila.mkdir(parents=True, exist_ok=True)

    # Analisa temas
    textos_validos = [t for t in transcricoes_texto if t]
    temas = analisar_temas(textos_validos)
    videos_ok = [(v, t) for v, t in zip(videos_info, transcricoes_texto) if t]

    titulo_doc = nome_base
    if playlist_nome:
        titulo_doc += f" - {playlist_nome}"

    apostila_path = pasta_apostila / f"APOSTILA - {titulo_doc}.md"

    # Calcula estatisticas
    total_min = sum(v.get("duration", 0) for v, _ in videos_ok) // 60
    total_palavras = sum(len(t.split()) for t in textos_validos)
    temas_principais = [t for t, c in temas.most_common(15)]

    with open(apostila_path, "w", encoding="utf-8") as md:
        md.write(f"""# 📚 APOSTILA DE ESTUDO

**Fonte:** {canal_nome}
""")
        if playlist_nome:
            md.write(f"**Playlist:** {playlist_nome}\n")
        md.write(f"""**Gerado em:** {datetime.now().strftime('%d/%m/%Y %H:%M')}
**Total de videos analisados:** {len(videos_ok)}
**Tempo total de conteudo:** ~{total_min} minutos
**Total de palavras transcritas:** ~{total_palavras}

---

## 1. CONHECIMENTO ADQUIRIDO

### Visao Geral do Conhecimento

Este material compila o conhecimento extraido de **{len(videos_ok)} videos** do canal **{canal_nome}**.
A seguir, uma sintese do que foi abordado:

""")

        # Gera descricao dos topicos principais
        if temas_principais:
            md.write("**Principais topicos de conhecimento:**\n\n")
            for tema in temas_principais[:10]:
                md.write(f"- **{tema}**\n")
            md.write("\n")

        # Sumario executivo de cada video
        md.write("### Resumo dos Videos\n\n")
        for i, (v, texto) in enumerate(videos_ok, 1):
            titulo_curto = v["title"][:100]
            md.write(f"**Video {i}:** {titulo_curto}")
            if v.get("duration"):
                md.write(f" ({v['duration']//60:02d}:{v['duration']%60:02d})")
            md.write("\n\n")
            # Primeiras linhas relevantes do video como resumo
            if texto:
                linhas = [l.strip() for l in texto.split("\n") if l.strip() and len(l.strip()) > 30]
                resumo = "\n".join(linhas[:5])
                md.write(f"> {resumo[:500]}\n\n" if resumo else "")
            md.write("---\n\n")

        md.write(f"""
---

## 2. CONTEUDO ABORDADO

### Estrutura de Temas

O conteudo foi organizado nos seguintes eixos tematicos:

""")

        # Cria capitulos por tema
        for tema, count in temas.most_common(15):
            if count < 3:
                continue
            md.write(f"""
### Capitulo: {tema}

> Tema mencionado **{count} vezes** nas transcricoes.
""")
            # Tenta extrair fragmentos relevantes
            fragmentos = _resumir_topico(tema, textos_validos)
            if fragmentos:
                md.write("**Trechos representativos:**\n\n")
                for i, frag in enumerate(fragmentos[:4], 1):
                    md.write(f"- \"{frag}...\"\n")
            md.write("\n")

        # Matriz de conhecimento
        md.write(f"""
### Matriz de Habilidades e Conhecimentos

| Tema | Nivel de Cobertura | Relevancia |
|------|-------------------|------------|
""")
        for tema, count in temas.most_common(20):
            nivel = "Alta" if count > 50 else ("Media" if count > 15 else "Introducao")
            relevancia = "Essencial" if count > 100 else ("Importante" if count > 30 else "Complementar")
            md.write(f"| {tema} | {nivel} | {relevancia} |\n")

        md.write(f"""
---

## 3. JORNADA DE APRENDIZADO

### Roteiro de Estudos Recomendado

Com base no material analisado, recomendamos a seguinte jornada de aprendizado:

**Fase 1 - Fundamentos** (comece por aqui)
""")

        # Pega videos mais introdutorios (pelos titulos)
        videos_intro = []
        videos_avancado = []
        for v, t in videos_ok:
            tit = v["title"].lower()
            if any(p in tit for p in ["basico", "introducao", "iniciante", "fundamento", "primeiro", "oque", "o que", "conceito"]):
                videos_intro.append((v, t))
            else:
                videos_avancado.append((v, t))

        if videos_intro:
            for v, _ in videos_intro:
                md.write(f"- [{v['title'][:80]}]({v.get('url', '#')})\n")
        else:
            # Pega os primeiros videos por data
            sorted_vids = sorted(videos_ok, key=lambda x: x[0].get("upload_date", ""))
            for v, _ in sorted_vids[:3]:
                md.write(f"- {v['title'][:80]}\n")
            md.write("\n*Nota: Nenhum video explicitamente introdutorio identificado. Os primeiros videos acima sao um ponto de partida.*\n")

        md.write(f"""
**Fase 2 - Aprofundamento**
""")
        for v, _ in videos_avancado[:5]:
            md.write(f"- {v['title'][:80]}\n")

        md.write(f"""
**Fase 3 - Sintese e Aplicacao**
""")
        if len(videos_ok) > 8:
            # Ultimos videos como sintese
            for v, _ in videos_ok[-3:]:
                md.write(f"- {v['title'][:80]}\n")
        md.write(f"""
### Carga Horaria Estimada

- Total de videos: **{len(videos_ok)}**
- Tempo total estimado: **~{total_min} minutos** (~{total_min//60}h{total_min%60:02d})
- Ritmo sugerido: **30-45 min/dia** (~{max(1, total_min//40)} dias para conclusao)

---

## 4. GLOSSARIO DE TERMOS

| Termo | Contexto | Frequencia |
|-------|----------|------------|
""")
        # Gera um glossario basico dos temas
        for tema, count in temas.most_common(25):
            desc = "Conceito central abordado no conteudo"
            md.write(f"| **{tema}** | {desc} | {count} menc. |\n")

        md.write(f"""
---

## 5. PROXIMOS PASSOS

### O que estudar a seguir

Com base no conhecimento mapeado, sugere-se:

1. **Revisar os temas com menor cobertura** na Matriz de Conhecimento
2. **Praticar os conceitos** em cenarios reais
3. **Aprofundar** nos topicos marcados como 'Essenciais'
4. **Explorar canais complementares** que abordem os mesmos temas sob diferentes perspectivas

---

## 6. REFERENCIAS

### Videos Analisados

| # | Titulo | Duracao |
|---|--------|---------|
""")
        for i, (v, _) in enumerate(videos_ok, 1):
            dur_str = f"{v['duration']//60:02d}:{v['duration']%60:02d}" if v.get('duration') else "?"
            md.write(f"| {i} | {v['title'][:80]} | {dur_str} |\n")

        if erros:
            md.write(f"\n### Videos nao processados\n\n")
            for e in erros:
                md.write(f"- {e.get('title', '?')} - {e.get('motivo', 'desconhecido')}\n")

        md.write(f"""
---

*Documento gerado automaticamente pelo **Baixar KnowHow** em {datetime.now().strftime('%d/%m/%Y as %H:%M')}.*
""")

    log(f"Apostila gerada: {apostila_path.name}")
    return apostila_path


def gerar_playbooks(info_canal, videos_info, transcricoes_texto, erros):
    """
    Gera PLAYBOOKS (guias praticos) para cada tema principal.
    Cada playbook contem:
    - Conceito central
    - Passo a passo
    - Acoes praticas
    - Referencias dos videos
    """
    APOSTILAS.mkdir(parents=True, exist_ok=True)

    canal_nome = info_canal.get("channel") or info_canal.get("uploader") or "Canal Desconhecido"
    nome_base = nome_arquivo_seguro(canal_nome, 50)
    pasta_playbooks = APOSTILAS / nome_base / "playbooks"
    pasta_playbooks.mkdir(parents=True, exist_ok=True)

    textos_validos = [t for t in transcricoes_texto if t]
    temas = analisar_temas(textos_validos)
    videos_ok = [(v, t) for v, t in zip(videos_info, transcricoes_texto) if t]

    # Se nao tem temas suficientes, cria playbooks baseados nos titulos dos videos
    temas_para_playbook = []
    for tema, count in temas.most_common(15):
        if count >= 2:  # threshold baixo: 2 mencoes ja vira playbook
            temas_para_playbook.append((tema, count))

    # Se ainda assim nao tem temas, cria a partir de palavras dos titulos
    if not temas_para_playbook and videos_ok:
        # Extrai palavras mais comuns dos titulos
        palavras_titulo = Counter()
        for v, _ in videos_ok:
            for palavra in re.findall(r'\b[A-Za-zÀ-ú]{4,}\b', v.get("title", "")):
                palavras_titulo[palavra.lower()] += 1
        # Pega as 5 palavras mais frequentes como temas
        for palavra, count in palavras_titulo.most_common(5):
            if count >= 2:
                temas_para_playbook.append((palavra.capitalize(), count))

    playbooks_gerados = []

    for tema, count in temas_para_playbook:
        nome_playbook = nome_arquivo_seguro(tema, 40)
        pb_path = pasta_playbooks / f"PLAYBOOK - {nome_playbook}.md"

        # Encontra videos relacionados ao tema (busca no texto e no titulo)
        videos_relacionados = []
        palavras_chave = tema.lower().split("/")[0].strip()[:20]
        # Limpa caracteres especiais para regex
        palavras_chave = re.sub(r'[\\\^$*+?{}()|\[\]]', '', palavras_chave)
        if not palavras_chave:
            palavras_chave = tema.lower()[:10]

        for v, t in videos_ok:
            # Busca no texto da transcricao
            no_texto = t and re.search(rf"(?i)\b{palavras_chave}\b", t)
            # Busca no titulo do video
            no_titulo = re.search(rf"(?i)\b{palavras_chave}\b", v.get("title", ""))
            if no_texto or no_titulo:
                videos_relacionados.append((v, t))
            if len(videos_relacionados) >= 8:
                break

        # Se nenhum video especifico, pega os primeiros videos
        if not videos_relacionados:
            videos_relacionados = videos_ok[:5]

        with open(pb_path, "w", encoding="utf-8") as pb:
            pb.write(f"""# PLAYBOOK: {tema}

**Fonte:** {canal_nome}
**Gerado em:** {datetime.now().strftime('%d/%m/%Y %H:%M')}
**Mencoes no material:** {count}

---

## Conceito Central

{tema} e um dos temas mais abordados no conteudo do canal **{canal_nome}**,
com {count} mencoes ao longo dos videos analisados.

### O que voce precisa saber:

1. **Definicao:** {tema} refere-se ao conjunto de conceitos e praticas relacionados a este topico.
2. **Importancia:** E um pilar fundamental do conhecimento transmitido pelo canal.
3. **Aplicacao:** Os conceitos sao aplicados em cenarios praticos de investimentos e financas.

---

## Passo a Passo

Com base no material estudado, o aprendizado de {tema.lower()} segue esta sequencia:

""")
            # Extrai passo-a-passo do texto (aceita linhas mais curtas)
            passos_encontrados = 0
            for v, texto in videos_relacionados[:3]:
                if not texto:
                    continue
                linhas = [l.strip() for l in texto.split("\n") if l.strip() and len(l.strip()) > 15]
                for linha in linhas[:4]:
                    passos_encontrados += 1
                    pb.write(f"**Passo {passos_encontrados}:** {linha[:300]}\n\n")
                    if passos_encontrados >= 8:
                        break
                if passos_encontrados >= 8:
                    break

            if passos_encontrados == 0:
                pb.write(f"*Os videos do canal abordam {tema.lower()} de forma pratica. Assista a sequencia recomendada abaixo para absorver o conteudo.*\n\n")

            pb.write(f"""---

## Acoes Praticas

- [ ] Identifique os conceitos de {tema.lower()} no seu dia a dia
- [ ] Aplique as estrategias discutidas nos videos
- [ ] Acompanhe a evolucao do seu entendimento
- [ ] Aprofunde com os videos recomendados abaixo

---

## Videos de Referencia

| # | Titulo | Duracao |
|---|--------|---------|
""")
            for i, (v, _) in enumerate(videos_relacionados, 1):
                dur_str = f"{v['duration']//60:02d}:{v['duration']%60:02d}" if v.get('duration') else "?"
                pb.write(f"| {i} | {v['title'][:80]} | {dur_str} |\n")

            pb.write(f"""
---

## Proximos Passos

1. Assista os videos na ordem recomendada
2. Faca anotacoes sobre os pontos principais
3. Tente explicar os conceitos para outra pessoa
4. Aplique o aprendizado em situacoes reais

---

*Playbook gerado automaticamente pelo **Baixar KnowHow** em {datetime.now().strftime('%d/%m/%Y as %H:%M')}.*
""")

        log(f"Playbook gerado: {pb_path.name}")
        playbooks_gerados.append(pb_path)

    # Gera um indice de playbooks
    if playbooks_gerados:
        indice_path = pasta_playbooks / "INDICE - Playbooks.md"
        with open(indice_path, "w", encoding="utf-8") as idx:
            idx.write(f"""# Indice de Playbooks - {nome_base}

**Total de playbooks:** {len(playbooks_gerados)}

| # | Playbook | Tema |
|---|----------|------|
""")
            for i, pb_path in enumerate(playbooks_gerados, 1):
                nome_pb = pb_path.stem.replace("PLAYBOOK - ", "")
                link = pb_path.name
                idx.write(f"| {i} | [{nome_pb}]({link}) | {nome_pb} |\n")

            idx.write(f"""
---

*Indice gerado automaticamente pelo **Baixar KnowHow** em {datetime.now().strftime('%d/%m/%Y as %H:%M')}.*
""")
        log(f"Indice de playbooks gerado: {indice_path.name}")

    return playbooks_gerados


def gerar_apostila_e_playbooks(info_canal, videos_info, transcricoes_texto, erros):
    """Gera apostila + playbooks e retorna os caminhos."""
    apostila = gerar_apostila(info_canal, videos_info, transcricoes_texto, erros)
    playbooks = gerar_playbooks(info_canal, videos_info, transcricoes_texto, erros)

    canal_nome = info_canal.get("channel") or info_canal.get("uploader") or "Canal Desconhecido"
    nome_base = nome_arquivo_seguro(canal_nome, 50)
    pasta = APOSTILAS / nome_base

    log(f"\n>> Apostila e Playbooks salvos em: {pasta}")
    return apostila, playbooks


def gerar_apostila_de_material_existente(canal_nome=None):
    """
    Escaneia as pastas transcricoes/ e knowhow/ para material ja baixado
    e gera apostila + playbooks.
    Se canal_nome for None, mostra os canais disponiveis.
    """
    if not TRANSCRICOES.exists():
        log("Nenhuma pasta transcricoes/ encontrada.", "ERRO")
        return False

    # Lista canais disponiveis
    canais = sorted([d.name for d in TRANSCRICOES.iterdir() if d.is_dir()])

    if not canais:
        log("Nenhum canal encontrado em transcricoes/", "ERRO")
        return False

    if canal_nome:
        # Filtra pelo nome
        canais_filtrados = [c for c in canais if canal_nome.lower() in c.lower()]
        if not canais_filtrados:
            log(f"Canal '{canal_nome}' nao encontrado. Disponiveis: {', '.join(canais)}", "ERRO")
            return False
        canais = canais_filtrados

    for canal in canais:
        log(f"Processando material existente: {canal}")

        # Le as transcricoes
        pasta_canal = TRANSCRICOES / canal
        txts = sorted(pasta_canal.glob("*.txt"))
        if not txts:
            log(f"Nenhum arquivo de transcricao em {canal}", "AVISO")
            continue

        videos_info = []
        transcricoes_texto = []

        for txt_path in txts:
            conteudo = txt_path.read_text(encoding="utf-8", errors="replace")
            # Extrai metadata do cabecalho
            titulo = "Video"
            video_id = txt_path.stem.split("__")[-1] if "__" in txt_path.stem else ""
            canal_nome_real = canal

            # Tenta extrair do cabecalho
            cab_match = re.search(r"TRANSCRI..O [—\-] (.+)", conteudo[:500])
            if cab_match:
                titulo = cab_match.group(1).strip()

            url = f"https://www.youtube.com/watch?v={video_id}" if video_id else ""

            videos_info.append({
                "id": video_id,
                "title": titulo,
                "url": url,
                "duration": 0,
                "upload_date": "",
                "channel": canal_nome_real,
                "channel_url": "",
                "description": "",
                "playlist": "",
            })

            # Remove cabecalho do texto
            texto_limpo = re.sub(r"^.+\n.+\n.+\n.+\n.+\n.+\n.+\n", "", conteudo, count=1, flags=re.DOTALL)
            texto_limpo = texto_limpo.strip()
            transcricoes_texto.append(texto_limpo)

        info_canal = {
            "channel": canal,
            "uploader": canal,
            "channel_url": "",
            "playlist_title": "",
            "title": f"Material do canal {canal}",
        }

        log(f"  -> {len(videos_info)} videos carregados")

        # Gera apostila e playbooks
        gerar_apostila_e_playbooks(info_canal, videos_info, transcricoes_texto, [])

    return True


# ══════════════════════════════════════════════════════════════════════════
#  6. PROCESSAMENTO PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════

def processar(urls=None, processar_pasta=False):
    """Função principal: recebe lista de URLs e processa tudo."""

    log("=" * 60)
    log("Baixar KnowHow - Iniciando extracao de conhecimento")
    log("=" * 60)

    todos_videos = []
    info_canal_global = {}

    if processar_pasta:
        log("Escaneando pasta baixados/ para videos ja baixados...")
        videos_pasta = listar_videos_da_pasta()
        if videos_pasta:
            log(f"Encontrados {len(videos_pasta)} videos na pasta baixados/")
            todos_videos.extend(videos_pasta)
            info_canal_global["channel"] = "Videos da pasta baixados"
        else:
            log("Nenhum video encontrado na pasta baixados/", "AVISO")

    if urls:
        for url in urls:
            url = url.strip()
            if not url:
                continue
            log(f"Analisando: {url}")
            try:
                info = extrair_info(url)
                if not info:
                    log(f"Não foi possível extrair info de: {url}", "ERRO")
                    continue

                # Guarda metadados do canal
                for key in ("channel", "uploader", "channel_url", "uploader_url", "playlist_title", "title"):
                    if info.get(key):
                        info_canal_global[key] = info.get(key)

                videos = listar_videos(info)
                log(f"Vídeos encontrados: {len(videos)}")
                todos_videos.extend(videos)

            except Exception as e:
                log(f"Erro ao processar {url}: {e}", "ERRO")

    if not todos_videos:
        log("NENHUM video encontrado!", "ERRO")
        log("")
        log("Possiveis causas:")
        log("  1. O YouTube esta bloqueando a extracao sem autenticacao")
        log("  2. Coloque um arquivo cookies.txt na pasta (exportado do navegador)")
        log("     Use extensao 'Get cookies.txt' (Chrome) ou 'cookies.txt' (Firefox)")
        log("  3. O canal pode estar restrito ou nao ter videos publicos")
        log("  4. Tente usar o link exato de uma playlist: https://youtube.com/playlist?list=...")
        log("  5. Use a opcao 'Processar videos da pasta baixados/' se ja baixou os videos")
        return

    log(f"\nTotal de vídeos a processar: {len(todos_videos)}")

    # ── Pool de threads para processar vídeos em paralelo ──────────
    MAX_WORKERS = 4  # número de threads simultâneas
    log(f"Usando {MAX_WORKERS} threads paralelas")

    transcricoes = [None] * len(todos_videos)
    erros = []
    log_lock = threading.Lock()

    def processar_video(idx, video):
        """Processa um único vídeo (thread-safe)."""
        titulo_curto = video["title"][:60]
        with log_lock:
            log(f"[{idx+1}/{len(todos_videos)}] {titulo_curto}...")

        texto = None
        idioma = None

        # Tenta 1: Legendas do YouTube
        texto, idioma = baixar_legendas(video)
        if texto:
            with log_lock:
                log(f"  [{idx+1}] Legendas OK ({idioma})")
        else:
            with log_lock:
                log(f"  [{idx+1}] Sem legendas, tentando transcricao local...")
            texto, idioma = transcrever_local(video)

        if texto:
            salvar_transcricao(video, texto, idioma)
            return idx, texto, None
        else:
            with log_lock:
                log(f"  [{idx+1}] Sem transcricao disponivel", "AVISO")
            return idx, None, {**video, "motivo": "sem legendas e sem whisper disponivel"}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futuros = {
            executor.submit(processar_video, idx, video): idx
            for idx, video in enumerate(todos_videos)
        }

        for futuro in as_completed(futuros):
            try:
                idx, texto, erro_info = futuro.result()
                transcricoes[idx] = texto
                if erro_info:
                    erros.append(erro_info)
            except Exception as e:
                idx_orig = futuros[futuro]
                log(f"Thread {idx_orig+1} falhou: {e}", "ERRO")
                transcricoes[idx_orig] = None
                erros.append({**todos_videos[idx_orig], "motivo": str(e)})

    # Remove None do final se todos foram preenchidos (segurança)
    transcricoes = transcricoes[:len(todos_videos)]

    # Compila o knowhow
    log("\nCompilando KnowHow em Markdown...")
    md_path = compilar_knowhow(info_canal_global, todos_videos, transcricoes, erros)

    log("\n" + "=" * 60)
    log("✅ Processo concluído!")
    log(f"   📄 KnowHow: {md_path}")
    log(f"   📁 Transcrições: {TRANSCRICOES}")
    log(f"   ✅ Vídeos processados: {len(todos_videos)}")
    log(f"   ✅ Com transcrição: {len([t for t in transcricoes if t])}")
    log(f"   ❌ Sem transcrição: {len(erros)}")
    log("=" * 60)

    # Pergunta se quer gerar apostila e playbooks
    try:
        resp = input("\n>> Gerar APOSTILA e PLAYBOOKS do material? (s/N): ").strip().lower()
        if resp in ("s", "sim", "y", "yes"):
            gerar_apostila_e_playbooks(info_canal_global, todos_videos, transcricoes, erros)
    except (EOFError, KeyboardInterrupt):
        pass

    return info_canal_global, todos_videos, transcricoes


# ══════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) > 1:
        if "--pasta" in sys.argv or "--processar-pasta" in sys.argv:
            processar(processar_pasta=True)
        elif "--apostila" in sys.argv or "--gerar-apostila" in sys.argv:
            # Gera apostila de material existente
            args = [a for a in sys.argv[1:] if not a.startswith("--")]
            canal_alvo = args[0] if args else None
            gerar_apostila_de_material_existente(canal_alvo)
        elif sys.argv[1].endswith(".txt"):
            with open(sys.argv[1], encoding="utf-8") as f:
                urls = [linha.strip() for linha in f if linha.strip()]
            processar(urls)
        else:
            urls = [a for a in sys.argv[1:] if not a.startswith("--")]
            processar(urls)
        return

    # Modo interativo
    while True:
        print("\n" + "╔══════════════════════════════════════╗")
        print("║      Baixar KnowHow — Extrator        ║")
        print("╚══════════════════════════════════════╝")
        print("1 - Colar link e processar")
        print("2 - Ler links de arquivo .txt")
        print("3 - Processar videos da pasta baixados/")
        print("4 - Gerar APOSTILA + PLAYBOOKS (material ja baixado)")
        print("5 - Sair")
        op = input("Opcao: ").strip()

        if op == "1":
            url = input("Link: ").strip()
            if url:
                processar([url])
        elif op == "2":
            path = input("Caminho do .txt: ").strip()
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as f:
                    urls = [linha.strip() for linha in f if linha.strip()]
                processar(urls)
            else:
                log("Arquivo nao encontrado.", "ERRO")
        elif op == "3":
            processar(processar_pasta=True)
        elif op == "4":
            gerar_apostila_de_material_existente()
        elif op == "5":
            break


if __name__ == "__main__":
    main()