# KEE-SKILL — Knowledge Extractor Engine

**Skill para agentes de IA que extrai conhecimento de canais YouTube e gera novas skills.**

---

## O que esta skill faz

Quando o usuário pedir, você deve ser capaz de:

| Pedido do usuário | O que você faz |
|------------------|----------------|
| "Baixa o canal X" | Extrai transcrições de todos os vídeos |
| "Me ajuda a estudar Y" | Gera apostila com os temas do canal |
| "Quero o playbook de Z" | Gera guia prático por tema |
| "Cria uma skill com esse conhecimento" | Gera um arquivo `.skill.md` que outros agentes podem instalar |
| "Qual o know-how desse canal?" | Compila temas, assuntos e resumo |

---

## 1. COMO BAIXAR AS TRANSCRIÇÕES

### 1.1 Descobrir os vídeos do canal/playlist

Use `yt-dlp` com `--flat-playlist` para listar rápido:

```bash
yt-dlp --flat-playlist --print "%(id)s|%(title)s|%(duration)s|%(upload_date)s" "URL_DO_CANAL_OU_PLAYLIST"
```

Se não voltar nada, tente com o formato de playlist de uploads:
- `https://www.youtube.com/channel/UC_ID/videos`
- `https://www.youtube.com/playlist?list=UU${CHANNEL_ID:2}`

### 1.2 Baixar as legendas de cada vídeo

```bash
yt-dlp --write-auto-subs --sub-langs "pt,en" --skip-download --convert-subs srt -o "transcricoes/Canal/%(title)s" "URL_DO_VIDEO"
```

Processe em lotes de 4 em 4 (paralelo) para ser mais rápido.

### 1.3 Se não tiver legenda, transcreva com Whisper

```bash
yt-dlp -f bestaudio -x --audio-format wav -o "tmp/%(id)s.%(ext)s" "URL_DO_VIDEO"
```

Depois use Python com faster-whisper ou openai-whisper para transcrever o áudio.

### 1.4 Organização das transcrições

Salve cada transcrição em:
```
transcricoes/NomeDoCanal/
  NomeDoVideo__VIDEOID.txt
```

Formato do arquivo:
```
TRANSCRIÇÃO — Nome do Vídeo
Canal: Nome do Canal
ID: videoID

[texto da transcrição aqui]
```

---

## 2. COMO GERAR O KNOWHOW

Após ter as transcrições, crie `knowhow/NomeDoCanal.md` com:

```markdown
# KnowHow Extraído

**Canal:** Nome do Canal
**Vídeos processados:** N
**Com transcrição:** N

## Temas e Assuntos Recorrentes

| Tema | Menções |
|------|---------|
| Tema 1 | 999 |
| Tema 2 | 999 |

## Lista de Vídeos

| # | Título | Duração | Status |
|---|--------|---------|--------|
| 1 | Vídeo | 10:30 | ✅ |

## Transcrições Completas

### 1. Título do Vídeo

```
texto da transcrição (primeiros 3000 caracteres)
```
```

Para identificar os temas, analise as palavras mais frequentes nas transcrições e agrupe por assunto.

---

## 3. COMO GERAR APOSTILA

Crie `apostilas/NomeDoCanal/APOSTILA - NomeDoCanal.md` no formato:

```markdown
# 📚 APOSTILA DE ESTUDO

**Fonte:** Nome do Canal
**Vídeos:** N
**Carga horária:** ~X minutos

## 1. CONHECIMENTO ADQUIRIDO

### Síntese do Conteúdo

[Liste os principais conceitos aprendidos]

### Resumo dos Vídeos

**Vídeo 1:** Título
> Trecho relevante da transcrição...

---

## 2. CONTEÚDO ABORDADO

### Eixos Temáticos

**Tema 1** (X menções)
- Conceito: [descrição]
- Trechos: "citação relevante..."

### Matriz de Conhecimento

| Tema | Cobertura | Relevância |
|------|-----------|------------|
| Tema | Alta/Média/Introdução | Essencial/Importante/Complementar |

## 3. JORNADA DE APRENDIZADO

**Fase 1 — Fundamentos**
- Vídeo A
- Vídeo B

**Fase 2 — Aprofundamento**
- Vídeo C
- Vídeo D

**Fase 3 — Síntese**
- Vídeo E

## 4. GLOSSÁRIO

| Termo | Significado | Contexto |
|-------|-------------|----------|
| Termo | Definição | Como é usado no canal |

## 5. REFERÊNCIAS

Lista de todos os vídeos com links.
```

---

## 4. COMO GERAR PLAYBOOKS

Para cada tema principal (mínimo 2 menções), crie um playbook em:
`apostilas/NomeDoCanal/playbooks/PLAYBOOK - Tema.md`

```markdown
# PLAYBOOK: Nome do Tema

**Menções no material:** X

## Conceito Central

[Explicação do tema baseada nas transcrições]

## Passo a Passo

1. Primeiro passo extraído dos vídeos...
2. Segundo passo...
3. Terceiro passo...

## Ações Práticas

- [ ] Ação 1
- [ ] Ação 2

## Vídeos de Referência

1. Título do vídeo 1
2. Título do vídeo 2
```

Depois crie `apostilas/NomeDoCanal/playbooks/INDICE - Playbooks.md` listando todos.

---

## 5. COMO GERAR UMA NOVA SKILL (META-SKILL)

Depois de processar um canal, pergunte ao usuário:

> "Quer gerar uma skill de IA com esse conhecimento?"

Se sim, crie `skills-geradas/KEE-NomeDoCanal.skill.md`:

```markdown
# KEE-SKILL: Nome do Canal

**Skill gerada a partir do canal:** Nome do Canal
**Vídeos analisados:** N
**Temas:** Tema1, Tema2, Tema3

## Descrição

Esta skill contém o conhecimento do canal [link].

## Conteúdo

- Apostila: `apostilas/Nome/APOSTILA - Nome.md`
- Playbooks: `apostilas/Nome/playbooks/`
- Transcrições: `transcricoes/Nome/`

## Como usar

Quando o usuário perguntar sobre [temas], use os arquivos acima como referência.
```

---

## 6. MODO INTERATIVO (GUIA PARA O USUÁRIO)

Quando o usuário interagir com você usando esta skill:

1. **Pergunte o link** se ele não forneceu
2. **Execute** o passo a passo acima
3. **Mostre o resumo** após processar
4. **Pergunte** se quer:
   - Ver o KnowHow
   - Ver a Apostila
   - Ver os Playbooks
   - Gerar uma Skill
5. **Salve tudo** na estrutura de pastas correta

---

## 7. EXEMPLO COMPLETO

**Usuário:** "Quero aprender trading, usa o canal Buraco de Minhoca"

**Você faz:**
1. `yt-dlp --flat-playlist --print "%(id)s|%(title)s" "https://youtube.com/@buracominhoca"`
2. Para cada vídeo, baixa legendas
3. Gera `knowhow/Buraco de Minhoca Quantitative Trading System.md`
4. Gera `apostilas/Buraco de Minhoca Canal/APOSTILA - ....md`
5. Gera playbooks: Gauss, Forex, Risco, etc.
6. Pergunta se quer gerar skill
7. Se sim, gera `skills-geradas/KEE-Buraco de Minhoca.skill.md`

---

## 8. DEPENDÊNCIAS (o ambiente já deve ter)

- `yt-dlp` — para baixar legendas e info dos vídeos
- `faster-whisper` ou `openai-whisper` — transcrição local (fallback)
- Python — para processar textos
- Acesso à internet — para YouTube

---

*KEE-SKILL v1.0 — Knowledge Extractor Engine*
*Uma skill que gera skills a partir de canais do YouTube.*