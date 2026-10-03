---
name: animated-captions
description: Cria legendas animadas palavra por palavra (estilo Hormozi/TikTok/karaoke) a partir dos timestamps da transcricao e queima no video com FFmpeg/libass. Use SEMPRE que o video for para redes sociais, quando o usuario pedir legenda, "subtitle", "caption", "legenda dinamica", ou quando o clipe tiver fala - a maioria assiste sem som, entao legenda e padrao em todo corte.
---

# animated-captions

Pre-requisito: `work/transcript.words.json` (lista `[{"word","start","end"}]` em segundos).

## Fluxo

1. **Revise a transcricao** contra o `glossary` (nomes, jogos, marcas, girias). Corrija a grafia sem mexer nos tempos. Texto de legenda deve ser fiel ao que foi dito.
2. **Gere o ASS** do clipe. Se o clipe comeca em `start` segundos do video fonte, use `--offset -start`:
   ```
   python .claude/skills/animated-captions/scripts/words_to_ass.py work/transcript.words.json \
       -o work/c01.ass --style hormozi --offset -123.4 --clip-duration 48.5
   ```
   Se houver cortes internos (silencios removidos), recalcule os tempos das palavras para a nova linha do tempo ANTES de gerar o ASS (some o tempo removido que veio antes de cada palavra).
3. **Queime no video** (rode dentro da pasta do `.ass` para evitar problemas de caminho com `C:\` no Windows):
   ```
   ffmpeg -i clipe.mp4 -vf "ass=c01.ass" -c:v libx264 -crf 18 -pix_fmt yuv420p -c:a copy saida.mp4
   ```
   Pode combinar com outros filtros: `...,ass=c01.ass` no fim da cadeia, para a legenda ficar por cima de tudo.
4. **Olhe os frames** (`extract_frames.py`) e confirme: cabe na largura, nao cobre rosto/HUD, esta legivel sobre qualquer fundo.

## Estilos do script
| Estilo | Visual | Quando usar |
|---|---|---|
| `hormozi` | maiusculas, negrito, contorno grosso, palavra atual amarela e maior | shorts de alta energia, opiniao, gameplay |
| `karaoke` | normal, palavra atual em dourado | conteudo neutro, musical |
| `minimal` | simples, branco com contorno | palestra, tutorial, tom serio, comercial |

Ajustes uteis: `--max-words 2..4`, `--size`, `--margin-v` (distancia da borda de baixo), `--font`, `--width/--height` (use 1920x1080 em video horizontal).

## Regras de legibilidade
- Maximo 3-4 palavras por vez, no maximo 2 linhas, nunca quebrar o nome proprio no meio.
- Fonte grossa com contorno escuro; contraste alto. Tamanho reduz sozinho se a linha nao couber.
- Posicao: terco inferior, acima da area de interface da plataforma. Em gameplay, suba a legenda se cobrir HUD.
- A legenda fica na tela enquanto a fala acontece; sem "piscar" em pausas curtas (o script segura a ultima palavra ~0.25 s).
- Acentos e `ç` precisam de fonte que os tenha; se a fonte pedida nao existir, o libass troca por outra: confira nos frames. No Windows, `Arial Black`, `Impact` e `Segoe UI Black` existem por padrao; para fonte propria use `fontsdir`:
  `-vf "ass=c01.ass:fontsdir=fonts"`.
- Palavroes: mantenha como falado, a menos que o usuario peca para censurar; avise se a plataforma de destino for sensivel.

## Alternativa mais rica
Para animacoes de entrada por palavra (pop, escala com mola, caixa colorida), use Remotion com `@remotion/captions` alimentado pelo mesmo JSON de palavras e renderize com a skill `motion-and-broll`. Use a rota ASS por padrao: e mais rapida e estavel.

## Erros comuns
- Tempo desalinhado = `--offset` errado ou cortes internos nao refletidos.
- Legenda cortada nas bordas = fonte maior que a largura; deixe o script calcular o tamanho.
- Legenda some ou aparece sem estilo = caminho do `.ass` com `:` ou `\` no filtro; copie o arquivo para a pasta de trabalho e use caminho relativo.
