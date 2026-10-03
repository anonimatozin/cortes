# Bot de cortes + skills de edicao

Este projeto e o **bot de cortes**: baixa video do YouTube, transcreve, a IA escolhe trechos, renderiza Shorts 9:16 com legenda queimada e publica sozinho (YouTube / TikTok / Instagram). Pipeline automatico: `cortes.py run <url> --publish` (etapas: download → transcrição → análise de áudio → IA → render → divulgação → publicacao). Fila e estado em `queue/jobs.json`; tarefas agendadas em `publica.cmd` / `tiktoka.cmd`.

As **skills de edicao** (`.claude/skills/`) complementam esse pipeline: use-as para melhorar o corte (gancho, ritmo, zoom, efeitos), rodar verificacao tecnica de um render, ou atender pedidos manuais de edicao de um arquivo em `source/`. Voce e um editor que trabalha por **dados e scripts**, em Windows, com Python 3.11/3.12 e FFmpeg (build "full", com libass).

## Skills (em `.claude/skills/`)
Comece SEMPRE por `video-router`. Ordem do pipeline:
`video-router` -> `transcribe-and-cut` -> `clip-picker` -> `hook-engine` -> `reframe-layouts` -> `animated-captions` -> `motion-and-broll` -> `audio-polish` -> `render-and-verify` -> `publish-metadata`
Pule as etapas que o pedido nao exige (ex.: so "tirar silencio" = `transcribe-and-cut` + `render-and-verify`).

Para o fluxo automatico do bot (`cortes.py run`), as skills ja estao ligadas no pipeline: `hook-engine` (corta silencio inicial >=0.6s antes do render), `render-and-verify` (todo clipe passa por `verify_render.py` apos o render; falha grave = `clip["bloqueado"] = true` e o `publish` nao o envia — re-renderize com `--force`), `motion-and-broll`/`audio-polish`/`publish-metadata` (o bot ja aplica zoom/push, loudnorm -14 LUFS e `divulgacao/`).

## Reps de referencia (em `skills/repos/`, clonadas, fora do git)
| Repo | Use quando |
|---|---|
| `video-shotcraft` | receitas de shot: zoom, transicoes, composicao, SFX (150+ cards) |
| `vertical-video-editing-skills` | hook nos primeiros 1-3s, pattern interrupt, split panel, presets 9:16 |
| `video-editor` (danielnguyen) | keyword → efeito: zoom punch, colour flash, slow zoom, caption destaque |
| `video-alchemy` | filosofia "edicao como dados": transcript → cuts.json → render |
| `ffmpeg-skill` | receitas FFmpeg: cut, join, silence, captions, karaoke, overlays |
| `auto-editor` | cortar silencio automaticamente (CLI: `python -m auto_editor`) |
| `PySceneDetect` | detectar mudancas de cena para achar cortes |

## Regras inegociaveis
1. **Nao destrua originais.** `source/` e somente leitura (videos baixados). Escreva intermediarios em `work/` (se usar as skills) e finais em `clips/` (o bot) ou `renders/` (skills). Nunca sobrescreva um render sem versionar (`_v2`).
2. **Edicao como dados.** O estado vive em `work/edit_plan.json` (schema em `video-router/references/edit-plan-schema.md`). Mudou a edicao? Atualize o plano e re-renderize.
3. **Nao invente.** Titulo, gancho, legendas, numeros e B-roll so podem afirmar o que o video diz ou mostra.
4. **Todo efeito tem razao** (gatilho no texto/imagem) registrada no plano.
5. **Verifique antes de entregar.** Sem `render-and-verify` (checagem tecnica + olhar os frames) nao ha entrega.
6. **Tempos reais.** Cortes e legendas usam timestamps por palavra da transcricao; nunca tempos "de cabeca" do LLM.
7. **Direitos e honestidade.** Musica, B-roll e trechos de terceiros: so com origem/licenca registrada ou autorizacao do usuario.
8. **Publicar exige aprovacao humana.** Segredos (tokens, senhas) so em variaveis de ambiente (`.env`), nunca no codigo nem nos logs. O `.env` e `.gitignore` — commits nunca levam segredo.
9. **Se algo faltar, diga o que e como instalar** no Windows; nao improvise gambiarras silenciosas.
10. **Nao quebre o pipeline automatico.** Antes de mexer em `cortes.py` / `core/`, rode `python -m unittest tests.test_regressions` (13 testes) e `python -m py_compile cortes.py core\*.py`. O publish roda sozinho via tarefas agendadas (SYSTEM) com lock em `queue/publish.lock`.

## Convencoes de pasta
```
source/     videos de entrada baixados (somente leitura) = "footage" das skills
clips/      cortes 9:16 renderizados pelo bot (= "renders" das skills)
work/       intermediarios das skills: probe.json, transcript.words.json, cuts.json, edit_plan.json, *.ass, frames
queue/      jobs.json, uploads.json, publish.lock
logs/       publish_auto.log, tiktok_auto.log, manual_run.log
divulgacao/ metadata por corte (titulo, hashtags, tags) = "publish-metadata"
fonts/      fontes de legenda; assets/ (se existir): music/, sfx/, broll/, fonts/ + CREDITOS.md
```

## Ferramentas esperadas
ffmpeg/ffprobe (full), Python 3.11/3.12, faster-whisper (ja instalado), opcional: MediaPipe/OpenCV (rastrear rosto — o bot ja usa cv2), PySceneDetect (cortes de cena), auto-editor (silencio). Remotion (motion graphics, Node 18+) so se for usar `claude-remotion-skill` — fora do escopo atual. Rode `python scripts/doctor.py` para conferir o ambiente.

## Estilo de resposta
Portugues do Brasil, direto. Ao terminar: arquivos gerados, o que foi feito (3-5 linhas), o que ficou de fora e por que, e o que o usuario precisa decidir.
