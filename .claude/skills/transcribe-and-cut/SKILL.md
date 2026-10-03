---
name: transcribe-and-cut
description: Transcreve o video com timestamps por palavra e faz a limpeza mecanica - remove silencios, pausas longas, erros, repeticoes e "hum/ne" - gerando cortes como dados (cuts.json) e um rough cut. Use SEMPRE antes de escolher trechos, adicionar legendas ou sincronizar efeitos com a fala; tambem quando o usuario pedir "tira os silencios", "corta os erros", "deixa mais dinamico" ou "transcreve".
---

# transcribe-and-cut

Tudo no resto do pipeline depende de **tempo por palavra**. Faca esta etapa bem.

## 1. Transcricao com tempo por palavra

Escolha, nesta ordem, o que estiver instalado (verifique com `pip list` / `python -c "import ..."`):
1. **faster-whisper** (rapido, usa GPU NVIDIA se houver): `word_timestamps=True`.
2. **WhisperX** (alinha melhor as palavras; opcional diarizacao para saber quem fala).
3. `openai-whisper` como ultimo recurso.

Regras:
- Idioma `pt` (ou o do plano). Modelo `medium` ou `large-v3` se a GPU aguentar; `small` para teste rapido.
- Passe como `initial_prompt` o `glossary` do `edit_plan.json` (nomes de jogos, pessoas, marcas) para a transcricao acertar os termos.
- Extraia o audio antes se o video for gigante: `ffmpeg -i in.mp4 -vn -ac 1 -ar 16000 work/audio.wav`.
- Salve `work/transcript.words.json` como lista `[{"word","start","end"}]` em segundos (formato que `animated-captions/scripts/words_to_ass.py` aceita) e `work/transcript.txt` legivel com marcas `[mm:ss]`.
- Palavras sem `start/end` (numeros, simbolos) devem ser interpoladas entre vizinhas, nunca descartadas do texto.
- Se o Whisper alucinar em trechos de musica/silencio (texto repetido, "Obrigado por assistir"), marque e ignore.

## 2. Silencio e pausas

```
python .claude/skills/transcribe-and-cut/scripts/detect_silence.py footage/in.mp4 -o work/cuts.json
python .claude/skills/transcribe-and-cut/scripts/detect_silence.py footage/in.mp4 -o work/cuts.json --render work/rough.mp4
```
Ajustes:
| Material | `--noise` | `--min-silence` | `--pad` |
|---|---|---|---|
| Voz limpa (podcast, estudio) | -35 | 0.4 | 0.08 |
| Voz com ruido de fundo/jogo | -28 a -30 | 0.5 | 0.10 |
| Estilo vlog agressivo | -35 | 0.3 | 0.05 |
| Aula/palestra (preservar ritmo) | -38 | 0.7 | 0.15 |

O script aplica fade de 20 ms em cada emenda de audio para nao estalar. Se a voz estiver sendo cortada, **diminua** `--noise` (ex.: -40) ou aumente `--pad`.

## 3. Erros, repeticoes e muletas

Com a transcricao em maos, procure e proponha cortes (nao aplique cegamente):
- Falsos comecos e frases repetidas ("eu fui... eu fui la").
- Muletas ("hum", "tipo", "ne") quando atrapalham; mantenha as que dao naturalidade.
- Trechos em que o orador se corrige: fique com a versao final.
- Cada corte vai para `clips[].cuts` com `reason`. Emende sempre em fronteira de palavra (use `end` da palavra anterior e `start` da seguinte, com respiro de ~60-80 ms).

## 4. Verificacao

- Ouca/inspecione as emendas: nenhuma palavra cortada pela metade, nenhum estalo.
- Compare duracao antes/depois e registre no resumo ("removi 41 s de silencio e 6 repeticoes").
- Se o usuario so pediu limpeza, entregue `work/rough.mp4` e pare aqui.
