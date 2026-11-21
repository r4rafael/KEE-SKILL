# KEE-SKILL — Knowledge Extractor Engine

> Transforme qualquer canal do YouTube em uma Skill de IA.

## 📥 Instalação

Para instalar esta skill no seu agente de IA:

```bash
# Clone o repositório
git clone https://github.com/r4rafael/KEE-SKILL.git
cd KEE-SKILL

# Ou simplesmente aponte o agente para o arquivo da skill
# KEE-SKILL.md
```

Depois de instalada, o agente saberá:

- **Baixar transcrições** de qualquer canal/playlist YouTube
- **Extrair o KnowHow** — temas, assuntos e conhecimento compilado
- **Gerar Apostilas** — livro de estudo completo
- **Gerar Playbooks** — guias práticos por tema
- **Gerar Skills** — criar novas skills de IA a partir do conhecimento extraído

## 🚀 Uso

Basta pedir ao agente:

> "Baixa o canal @BuracoDeMinhoca e me ajuda a estudar trading"

Ou:

> "Pega essa playlist https://youtube.com/playlist?list=... e cria uma skill com o conhecimento"

## 📁 Estrutura gerada

```
projeto/
├── transcricoes/NomeDoCanal/     ← Transcrições (.txt)
├── knowhow/NomeDoCanal.md        ← KnowHow compilado
├── apostilas/NomeDoCanal/        ← Apostila + Playbooks
│   ├── APOSTILA - Canal.md
│   └── playbooks/
└── skills-geradas/               ← Skills geradas (.skill.md)
    └── KEE-Canal.skill.md
```

## 🤖 Meta-Skill

O KEE é uma **skill que gera skills**:
1. Você cola um link do YouTube
2. O agente extrai TODO o conhecimento
3. O agente gera uma `.skill.md` com aquele conhecimento
4. Qualquer outro agente que instalar essa skill passa a ter o conhecimento do canal

---

**KEE-SKILL** — https://github.com/r4rafael/KEE-SKILL