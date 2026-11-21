# KEE-SKILL — Knowledge Extractor Engine

> Transforme qualquer canal do YouTube em uma Skill de IA.
> Skill que gera skills a partir de conteudo de canais.

## 📥 Instalação

```bash
git clone https://github.com/r4rafael/KEE-SKILL.git
cd KEE-SKILL
pip install -r requirements.txt
```

## 🚀 Uso

### Como agente (lendo a skill):

Aponte seu agente para `KEE-SKILL.md` — ele saberá como:

1. **Baixar transcricoes** de videos/playlists/canais
2. **Extrair KnowHow** — temas, assuntos, resumo
3. **Gerar Apostila** — livro de estudo completo
4. **Gerar Playbooks** — guias praticos por tema
5. **Gerar Skills** — criar novas `.skill.md` a partir do conhecimento

### Direto no terminal:

```bash
python src/baixar-knowhow.py "https://youtube.com/playlist?list=..."
python src/baixar-knowhow.py --pasta
python src/baixar-knowhow.py
```

## 📁 Estrutura

```
KEE-SKILL/
├── KEE-SKILL.md              ← Skill para agente (instrucoes)
├── README.md
├── skill.json                ← Manifesto
├── requirements.txt          ← Dependencias Python
├── install.bat               ← Instalador Windows
├── .gitignore
├── .github/workflows/       ← CI
├── src/
│   └── baixar-knowhow.py    ← Engine completa
└── examples/
    └── KEE-BuracoDeMinhoca.skill.md  ← Exemplo de skill gerada
```

## 🤖 Meta-Skill

O KEE e uma **skill que gera skills**:
1. Cole um link do YouTube
2. O agente extrai TODO o conhecimento
3. Gera uma `.skill.md` com aquele conhecimento
4. Qualquer outro agente que instalar essa skill passa a ter o conhecimento do canal

---

**KEE-SKILL** — https://github.com/r4rafael/KEE-SKILL