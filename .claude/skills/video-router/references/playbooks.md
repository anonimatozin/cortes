# Playbooks por tipo de video

Regras praticas (heuristicas de editores), nao leis. Ajuste ao que o material pedir e ao pedido do usuario.

Indice: 1 Podcast/entrevista - 2 Gameplay - 3 Live/stream - 4 Tutorial/screencast - 5 Vlog/talking head - 6 Palestra/aula - 7 React - 8 Comercial/produto - 9 Video longo horizontal (16:9) - 10 Video mudo/musica

---
## 1. Podcast / entrevista (2+ pessoas)
- **Cortes:** busque opiniao forte, historia com comeco-meio-fim, discordancia, numero surpreendente, confissao. Evite trechos que dependem de contexto anterior.
- **Reframe:** `face_track` no falante ativo; `split_2` (um em cima, outro embaixo) quando ha troca rapida. Nunca "passeie" a camera durante uma troca de cena.
- **Hook:** a frase mais forte do trecho vai para o inicio (cold open) se o clipe continuar verdadeiro; senao comece na melhor frase real.
- **Legendas:** sempre. Estilo `hormozi` ou `minimal`. Cuide dos nomes proprios (glossary).
- **Efeitos:** poucos. Punch-in sutil em palavra-chave; B-roll/card de numero quando citam dado. Deixe respirar nas risadas.
- **Audio:** equalize vozes diferentes com loudnorm; sem musica alta (conversa e o produto).

## 2. Gameplay (Minecraft, FPS, etc.)
- **Cortes:** momentos de acao + reacao: picos de volume da voz, risada, grito, clutch, fail engracado, descoberta. Use picos de energia de audio como candidatos e confirme na transcricao/frames.
- **Reframe:** sem rosto, use `blur_fit` (jogo centralizado com fundo desfocado) ou `center_crop` se a acao estiver no centro; com webcam, `gameplay_facecam` (webcam em cima, jogo embaixo). Mantenha HUD importante (vida, placar) visivel.
- **Hook:** comece no resultado ou no momento de tensao ("olha o que aconteceu"), nunca no menu/carregando/andando sem rumo.
- **Legendas:** so da fala do jogador; evite cobrir HUD e miras. Posicao no terco inferior pode bater com HUD: ajuste `--margin-v`.
- **Efeitos:** punch-in e shake na hora do impacto, freeze no fail, SFX curtos. Pode ser mais denso (um evento a cada 2-3 s).
- **Audio:** cuidado com musica de fundo do jogo/streamer (direitos autorais); prefira musica livre. Abaixe o som do jogo sob a voz.

## 3. Live / stream
- **Cortes:** da ao vivo para clipe exige MUITA triagem: ache o pico (chat, risada, vitoria) e corte com contexto minimo. Remova esperas e silencio com `transcribe-and-cut`.
- **Reframe:** `gameplay_facecam` ou `blur_fit`. Remova overlays de chat/doacao que fiquem ilegiveis em 9:16 se possivel.
- **Hook:** reacao + resultado. Evite "entao gente, como eu estava dizendo".
- **Audio:** normalize muito (lives variam), atenue ruido constante.

## 4. Tutorial / screencast
- **Cortes:** remova erros, pausas, "hum", cliques perdidos; acelere trechos de espera (1.5x-3x com marcador "acelerado").
- **Reframe:** `screen_cursor` (zoom que segue o cursor, sem tremer) ou recorte da regiao ativa; texto da tela precisa ficar legivel no celular.
- **Hook:** mostre o RESULTADO final primeiro ("isso aqui em 30 s"), depois o passo a passo.
- **Efeitos:** setas/destaques/caixas sobre o elemento clicado, zoom suave na regiao do que esta sendo explicado, numeracao de passos.
- **Legendas:** sim, e termos tecnicos no glossary.

## 5. Vlog / talking head solo
- **Cortes:** jump cuts agressivos (pausa > 0.35-0.4 s), remova repeticao e erro. Mantenha emocao e respiros que dao personalidade.
- **Reframe:** `face_track` suave; olhar da camera centralizado.
- **Hook:** afirmacao ousada, pergunta ou resultado nos primeiros segundos; saudacao longa vai para o fim ou some.
- **Efeitos:** punch-in alternado (dois enquadramentos) cria ritmo sem B-roll; B-roll quando citar lugar/objeto.

## 6. Palestra / aula / apresentacao
- **Cortes:** uma ideia completa por clipe (pergunta -> explicacao -> conclusao). Cuidado extra com cortar no meio de um raciocinio.
- **Reframe:** `face_track`; se houver slides, `split_2` (slide + palestrante) ou so o slide quando for o ponto.
- **Hook:** a pergunta ou a tese ("A maioria erra isso:").
- **Legendas:** essenciais; nomes e termos tecnicos no glossary. Efeitos minimos para nao desrespeitar o tom.

## 7. React (reacao a outro video)
- **Cuidados:** conteudo de terceiros - avise o usuario sobre direitos autorais/uso justo e mantenha o trecho original curto e comentado.
- **Layout:** original e reacao lado a lado ou empilhados; sincronize sempre o audio do original com a reacao.
- **Hook:** a reacao mais forte primeiro, depois o contexto.

## 8. Comercial / produto / marca
- **Cortes:** beneficio primeiro, prova depois, chamada para acao no fim. Duracao curta.
- **Texto:** so afirmacoes que o cliente pode comprovar; nao invente numeros, precos ou promessas.
- **Visual:** respeite identidade (cores, logo, fonte) se o usuario fornecer; sem isso, estilo limpo.
- **CTA final** explicito, legivel por 2-3 s.

## 9. Video longo horizontal (16:9, YouTube normal)
- **Objetivo diferente:** retencao em minutos, nao segundos. Cortes por ritmo e clareza; capitulos; sem reframe vertical.
- **Hook:** promessa clara + preview do melhor momento nos primeiros 10-15 s, depois contexto.
- **Efeitos:** B-roll e graficos para quebrar monotonia a cada 20-40 s; legendas opcionais (acessibilidade).
- **Entrega:** 1920x1080, 30 ou 60 fps conforme a fonte; tambem gere capitulos/descricao via `publish-metadata`.

## 10. Video mudo / so musica / visual
- Sem transcricao: corte no ritmo da musica (batidas) e por mudancas de cena (PySceneDetect).
- Hook: o quadro mais impactante nos primeiros 1-2 s. Texto na tela substitui a fala.
