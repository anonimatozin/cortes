# edit_plan.json - contrato entre as skills

Um arquivo por video fonte, em `work/edit_plan.json`. Tempos em segundos, sempre referentes ao video FONTE, salvo onde indicado.

```json
{
  "source": "footage/entrada.mp4",
  "probe": "work/probe.json",
  "type": "podcast | gameplay | live | tutorial | vlog | palestra | react | comercial | outro",
  "language": "pt-BR",
  "target": {
    "platform": "shorts | tiktok | reels | youtube | generico",
    "width": 1080, "height": 1920, "fps": 30,
    "min_duration": 20, "max_duration": 59
  },
  "glossary": ["nomes proprios", "jogos", "marcas que a transcricao deve acertar"],
  "transcript": "work/transcript.words.json",
  "clips": [
    {
      "id": "c01",
      "start": 123.4,
      "end": 171.9,
      "title_internal": "resumo curto para voce se achar",
      "score": 0,
      "why": "motivo da escolha",
      "hook": {
        "type": "resultado_primeiro | pergunta | afirmacao | contraste | numero | demonstracao | cold_open",
        "spoken": "frase falada que abre o clipe",
        "text_on_screen": "ate 7 palavras",
        "reorder": null
      },
      "cuts": [{"start": 130.0, "end": 130.6, "reason": "silencio"}],
      "layout": "center_crop | face_track | blur_fit | split_2 | gameplay_facecam | screen_cursor",
      "captions": {"style": "hormozi | minimal | karaoke", "file": "work/c01.ass"},
      "effects": [{"t": 2.0, "type": "punch_in | slow_push | flash | shake | freeze | card", "reason": "palavra-chave 'MUITO'"}],
      "broll": [{"t": 8.5, "dur": 2.0, "asset": "assets/broll/x.mp4", "reason": "cita o produto"}],
      "sfx": [{"t": 2.0, "file": "assets/sfx/whoosh.wav", "gain_db": -12}],
      "audio": {"music": null, "target_lufs": -14},
      "output": "renders/c01.mp4",
      "verify": null
    }
  ]
}
```

Regras:
- `clips[].start/end` sao do FONTE. `effects[].t`, `broll[].t`, `sfx[].t` sao relativos ao INICIO DO CLIPE FINAL (ja sem os cortes).
- Cada skill so escreve nos campos que lhe pertencem e nunca apaga os dos outros.
- `verify` recebe o resultado de `render-and-verify` (`passed`, avisos).
