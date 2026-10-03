---
name: motion-and-broll
description: Adiciona elementos de edicao que seguram a atencao - zoom punch-in, slow push, flash, shake, freeze, cards de texto/numero, destaques, B-roll e SFX - sempre ligados a palavras e momentos do video. Use SEMPRE depois do corte e das legendas, quando o usuario pedir "mais dinamico", "efeitos", "zoom", "B-roll", "motion graphics", "transicoes", ou quando o clipe parecer estatico (talking head parado, tela sem mudanca por mais de ~4 s).
---

# motion-and-broll

Principio: **efeito sem razao e poluicao.** Cada efeito nasce de um gatilho no texto ou na imagem e e registrado em `clips[].effects` com `reason`.

## 1. Mapa de gatilhos (palavra/momento -> efeito)

| Gatilho | Efeito | Notas |
|---|---|---|
| Palavra de enfase ("MUITO", "nunca", "impossivel") | `punch_in` | +8% a +15% por ~0.3 s |
| Frase-chave / virada | `slow_push` | 100% -> 108% em 3-4 s |
| Impacto, susto, resultado | `flash` + SFX | branco por 2-3 frames |
| Erro, fail, piada | `freeze` 0.4-0.8 s + SFX | congela e solta |
| Numero ou dado citado | `card` com o numero grande | mesmo valor dito; nunca invente |
| Lugar/objeto/pessoa citada | B-roll 1-3 s | so se mostrar o que foi dito |
| Pausa longa sem corte | corte para outro enquadramento (zoom 110-120%) | alterna "plano aberto / plano fechado" |
| Gameplay: kill, descoberta, queda | `shake` curto + punch_in + SFX | evite se atrapalhar o HUD |

## 2. Densidade (ritmo)
- Primeiros ~15 s: uma mudanca visual a cada ~2-4 s (zoom, corte, texto, B-roll). Depois relaxe para nao cansar.
- Espace de forma **irregular**; efeitos em intervalo identico viram metronomo.
- Talking head: alterne dois enquadramentos (aberto e 110-115% fechado) a cada frase/ideia.
- Nao empilhe mais de 2 efeitos no mesmo instante.
- Conteudo serio (palestra, comercial B2B, luto): reduza tudo, sem shake/flash.

## 3. Receitas FFmpeg testadas (video 1080x1920)

**Punch-in** (pulso triangular em T0=2 s, duracao 0.3 s, +12%). Troque `2` e `0.3`:
```
-vf "scale=w='1080*(1+0.12*max(0,1-abs(t-2)/0.3))':h=-2:eval=frame,crop=1080:1920"
```
Para varios punches some pulsos: `1+0.12*max(0,1-abs(t-2)/0.3)+0.12*max(0,1-abs(t-9.5)/0.3)`.

**Flash branco** de 2.0 a 2.1 s:
```
-vf "drawbox=x=0:y=0:w=iw:h=ih:color=white@0.8:t=fill:enable='between(t,2,2.1)'"
```

**Texto de gancho** (use `.ass` para estilizar melhor; `drawtext` serve para teste). Apenas enquanto `t<1.8`:
```
-vf "drawtext=text='ISSO MUDOU TUDO':fontfile=C\\:/Windows/Fonts/impact.ttf:fontsize=96:fontcolor=white:borderw=6:bordercolor=black:x=(w-text_w)/2:y=h*0.18:enable='lt(t,1.8)'"
```
No Windows, escape os dois-pontos do caminho da fonte como `C\\:/...`. Para textos com acentos ou muitos estilos, prefira escrever um segundo `.ass` de titulos.

**Freeze frame**: corte o trecho, use `trim` + `loop`/`tpad=stop_mode=clone:stop_duration=0.6` no clipe curto e concatene.

**B-roll** (sobrepor 2 s a partir de t=8.5, sem trocar o audio da fala):
```
-filter_complex "[1:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setpts=PTS-STARTPTS+8.5/TB[b];[0:v][b]overlay=enable='between(t,8.5,10.5)':eof_action=pass[v]"
```

## 4. B-roll - regras
- So quando reforca ou explica o que foi dito. Nunca "pra preencher".
- Fontes permitidas: material do proprio usuario em `assets/broll/`, bancos gratuitos com licenca clara (Pexels/Pixabay com API e a licenca registrada) ou gerado. Nada de recortar trecho de terceiros sem o usuario confirmar que pode.
- Duracao 1-3 s, entra e sai em corte seco ou fade curto. Mantenha o audio original da fala.
- Registre `asset`, `t`, `dur` e `reason` no plano; guarde a origem/licenca em `assets/broll/CREDITOS.md`.

## 5. SFX
- Curtos (whoosh em corte/zoom, impacto em flash/numero, pop em texto). Volume baixo (-12 a -18 dB abaixo da voz) e nunca no meio de uma palavra importante.
- Coloque cada SFX no tempo do efeito (`clips[].sfx`) e misture na skill `audio-polish`.

## 6. Quando usar Remotion em vez de FFmpeg
Use Remotion (React; cada frame e funcao do tempo, via `useCurrentFrame`, `interpolate`, `spring`) quando precisar de: cards animados, barras de progresso, listas aparecendo, legendas com pop por palavra, templates reaproveitaveis. Mantenha FFmpeg para corte, concatenacao, recortes, mixagem e codificacao. Confira a licenca do Remotion em remotion.dev/license antes de uso comercial em empresa.

## 7. Verificacao
Assista aos frames em torno de cada efeito (`extract_frames.py --times ...`): o efeito esta no momento certo? Esconde algo importante? Se ficou "demais", remova metade.
