---
name: audio-polish
description: Deixa o audio profissional - limpa a voz, normaliza o volume (loudness), abaixa a musica automaticamente quando a pessoa fala (ducking), mistura SFX e evita estalos nas emendas. Use SEMPRE antes do render final, e quando o usuario reclamar de "audio baixo", "ruido", "voz abafada", "musica alta", "volume diferente entre clipes" ou pedir musica de fundo.
---

# audio-polish

Audio ruim derruba video bom. Ordem da cadeia: **limpar voz -> misturar musica/SFX com ducking -> normalizar por ultimo.**

## 1. Diagnostico
Meça antes de mexer: `python .claude/skills/render-and-verify/scripts/verify_render.py clipe.mp4` mostra LUFS e pico. Ouça/inspecione: ha ruido constante? eco? picos? volume muito diferente entre falantes?

## 2. Limpeza da voz (so se precisar)
```
-af "highpass=f=80,afftdn=nf=-25,acompressor=threshold=-18dB:ratio=3:attack=15:release=250"
```
- `highpass` tira ronco grave; `afftdn` reduz ruido constante (comece leve, `nf` entre -20 e -30; forte demais deixa voz "aquosa").
- `acompressor` uniformiza a voz. Teste em 10 s antes de aplicar no clipe todo.
- Se a qualidade for muito ruim, avise o usuario em vez de prometer milagre.

## 3. Musica de fundo com ducking (testado)
A musica cai quando a voz fala e sobe nas pausas. A voz entra duas vezes no filtro (sinal e "chave"), por isso o `asplit`:
```
ffmpeg -i clipe.mp4 -stream_loop -1 -i assets/music/trilha.mp3 -filter_complex \
"[1:a]volume=0.35[m];[0:a]asplit=2[voz][key];[m][key]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=400[duck];[voz][duck]amix=inputs=2:duration=first:normalize=0[a]" \
-map 0:v -map "[a]" -c:v copy -c:a aac -b:a 192k -shortest saida.mp4
```
- Ajuste `volume=` da musica (0.2 a 0.4) ate ela ficar claramente abaixo da voz.
- Musica **sem direitos**: use faixas do usuario, biblioteca livre com licenca clara ou da propria plataforma. Registre a fonte em `assets/music/CREDITOS.md`. Nao use musica comercial sem o usuario confirmar que pode.
- Em podcast/entrevista, musica quase inaudivel ou nenhuma.

## 4. SFX
Posicione cada SFX do plano com `adelay` (milissegundos) e misture:
```
-i whoosh.wav -filter_complex "[1:a]adelay=2000|2000,volume=0.3[s];[0:a][s]amix=inputs=2:duration=first:normalize=0[a]"
```
Para varios SFX, gere cada `[sN]` e junte tudo num unico `amix` com `inputs=N+1`.

## 5. Emendas sem estalo
Cada corte de audio ganha fade de 10-30 ms (o `detect_silence.py --render` ja faz). Se emendar por conta propria: `afade=t=in:d=0.02` e `afade=t=out:d=0.02` em cada trecho.

## 6. Normalizacao final (por ultimo)
```
-af "loudnorm=I=-14:TP=-1.5:LRA=11"
```
- Alvo pratico para redes sociais: cerca de **-14 LUFS** integrado com pico real abaixo de -1 dBTP (as plataformas reajustam o volume; o importante e ficar consistente entre clipes). Em video longo/educacional, -16 LUFS tambem e comum.
- Uma passada serve para clipes curtos. Para precisao use duas passadas: meça com `loudnorm=print_format=json`, depois reaplique com `measured_I`, `measured_TP`, `measured_LRA`, `measured_thresh`.
- Re-encode o audio em AAC 192 kbps, 48 kHz.

## 7. Verificacao
Rode `verify_render.py` de novo: LUFS dentro da faixa, pico sem estourar, e ouca o inicio: a primeira palavra nao pode comecar baixa nem cortada.
