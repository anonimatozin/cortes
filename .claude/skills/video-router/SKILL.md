---
name: video-router
description: Porta de entrada de TODA tarefa de edicao de video. Use SEMPRE que o usuario entregar um video (ou pasta de videos) e pedir para editar, cortar, criar shorts/reels/tiktoks, melhorar, legendar ou "deixar viral" - mesmo que ele nao diga o tipo de video. Analisa o arquivo com ffprobe, descobre se e podcast, gameplay, live, tutorial, vlog, palestra, react ou comercial, escolhe o playbook certo e monta o edit_plan.json que as outras skills executam.
---

# video-router

Primeira skill a rodar. Ela NAO edita: ela entende o material e decide o caminho.

## Passo a passo

1. **Nunca mexa no original.** Copie ou trabalhe sempre a partir de `footage/` (somente leitura) e escreva em `work/` e `renders/`.
2. **Analise o arquivo:**
   ```
   python .claude/skills/video-router/scripts/probe_video.py footage/entrada.mp4 -o work/probe.json
   ```
   Registre duracao, resolucao, fps, orientacao e se tem audio. Sem audio = video mudo: pule transcricao e legendas de fala.
3. **Descubra o tipo de video.** Assista a amostras: extraia frames (skill `render-and-verify`, script `extract_frames.py --times`) em 5 a 8 pontos e leia as primeiras 60 s da transcricao. Se continuar em duvida, PERGUNTE ao usuario em uma unica pergunta curta.
4. **Leia o playbook do tipo** em `references/playbooks.md` (so a secao do tipo detectado).
5. **Defina o objetivo de saida** (pergunte so o que faltar): corte vertical curto, video horizontal editado, ou os dois? Plataforma (YouTube Shorts, TikTok, Reels, YouTube normal)? Quantos cortes? Verifique os limites de duracao ATUAIS de cada plataforma antes de fixar `max_duration`; na duvida use 20-60 s para cortes.
6. **Monte `work/edit_plan.json`** seguindo `references/edit-plan-schema.md`. Esse arquivo e o contrato: as outras skills leem e preenchem. A edicao e tratada como DADOS, nunca como cliques.
7. **Chame as skills nesta ordem** (pule as que o plano nao precisa):
   `transcribe-and-cut` -> `clip-picker` -> `hook-engine` -> `reframe-layouts` -> `animated-captions` -> `motion-and-broll` -> `audio-polish` -> `render-and-verify` -> `publish-metadata`

## Regras de ouro

- Nao invente fatos: titulo, texto de gancho e legendas so podem dizer o que o video realmente diz ou mostra.
- Edicao com proposito: cada efeito, corte ou B-roll precisa de uma razao ligada ao que esta sendo dito.
- Se o pedido for vago ("deixa bonito"), assuma o padrao do playbook e DIGA as suposicoes em uma linha.
- Varios videos de uma vez: processe um por vez, salvando `work/<nome>/` separado, e entregue um resumo no final.
- Se faltar ferramenta (ffmpeg, whisper), rode `python .claude/skills/video-router/scripts/probe_video.py` e explique exatamente o que instalar no Windows em vez de tentar contornar.

## Entrega ao usuario

Termine sempre com: arquivos gerados (caminhos), o que foi feito em 3-5 linhas, o que ficou de fora e por que, e o que o usuario precisa decidir.
