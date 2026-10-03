---
name: render-and-verify
description: Renderiza o video final com as configuracoes certas (H.264/AAC, NVENC com fallback), roda checagens tecnicas automaticas e INSPECIONA os frames dos primeiros 5 segundos e do resto do video antes de entregar, corrigindo e re-renderizando se algo estiver errado. Use SEMPRE como ultima etapa de qualquer edicao, e quando o usuario disser "ficou estranho", "confere o video", "ta com problema de audio/legenda" ou "revisa".
---

# render-and-verify

**Nada e entregue sem passar por aqui.** Gerar o arquivo nao e terminar; terminar e provar que ficou bom.

## 1. Render final

Padrao para vertical (ajuste se o plano pedir outro alvo):
```
ffmpeg -i entrada.mp4 -c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p -r 30 \
  -c:a aac -b:a 192k -ar 48000 -movflags +faststart renders/c01.mp4
```
- `yuv420p` e `+faststart` evitam video que nao abre em celular e demora para comecar.
- Mantenha o fps do alvo (30 padrao; 60 so se a fonte for 60 e o conteudo pedir, ex.: gameplay).

**GPU NVIDIA (NVENC)** - teste antes de usar; o encoder pode existir no build sem haver GPU:
```
ffmpeg -hide_banner -loglevel error -f lavfi -i color=c=black:s=256x256:d=0.2 -c:v h264_nvenc -f null -
```
Se retornar erro (codigo diferente de 0), use `libx264`. Se funcionar: `-c:v h264_nvenc -preset p5 -cq 19 -b:v 0 -pix_fmt yuv420p`.

Varios clipes: renderize um por vez, nomeando `renders/<id>.mp4`; nunca sobrescreva o render anterior sem guardar (`renders/c01_v1.mp4`, `_v2`...).

## 2. Checagem tecnica automatica
```
python .claude/skills/render-and-verify/scripts/verify_render.py renders/c01.mp4 --width 1080 --height 1920 --fps 30 --min-dur 15 --max-dur 59 --json work/c01.verify.json
```
Verifica resolucao, fps, duracao, codecs, `yuv420p`, audio, loudness, pico, preto e imagem congelada no inicio. Codigo de saida 1 = reprovado. "AVISO" nao reprova, mas explique no resumo.

## 3. Inspecao visual (obrigatoria)
```
python .claude/skills/render-and-verify/scripts/extract_frames.py renders/c01.mp4 -o work/c01_frames
```
**Abra as imagens** (use a ferramenta de visualizar imagens) e responda por escrito, curto:
1. **0-0.5 s:** ha mudanca/impacto imediato? Nao e tela preta/parada?
2. **0.5-3 s:** o texto/promessa do gancho esta legivel e na area segura?
3. **Legendas:** cabem, estao legiveis, nao cobrem rosto/HUD, sem caracteres quebrados (acentos)?
4. **Enquadramento:** o assunto principal esta inteiro em todos os frames?
5. **Efeitos/B-roll:** aparecem no momento certo? Algum esconde algo importante?
6. **Final:** termina limpo (sem corte no meio da palavra, sem tela preta)? Se possivel, termine de forma que emende com o comeco (loop).

Para checar sincronia, extraia frames em instantes onde a legenda mostra uma palavra especifica e compare com o audio (palavra no `transcript.words.json`).

## 4. Corrigir e repetir
- Se algo falhou, corrija na skill responsavel (legenda -> `animated-captions`, enquadramento -> `reframe-layouts`, volume -> `audio-polish`...), re-renderize como `_v2` e verifique de novo.
- Maximo de **3 ciclos** de correcao automatica. Se ainda houver problema, entregue a melhor versao, diga exatamente o que ficou pendente e por que.

## 5. Relatorio de entrega (modelo)
```
Clipe c01 - renders/c01.mp4 (1080x1920, 38.2 s, 30 fps, -14.1 LUFS)
Feito: gancho "..." (0.0-2.5 s), removi 9 s de silencio, legendas hormozi, 4 punch-ins, musica com ducking.
Verificacao: APROVADO (1 aviso: ...). Frames conferidos: 0, 0.3, 0.6, 1, 1.5, 2, 3, 4, 5, meio, fim.
Pendente/decisao sua: ...
```
Preencha `clips[].verify` no `edit_plan.json` com o resultado.
