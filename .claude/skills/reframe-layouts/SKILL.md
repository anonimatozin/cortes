---
name: reframe-layouts
description: Converte video horizontal (16:9) em vertical 9:16 e monta layouts - recorte central, seguir rosto do falante, tela dividida para duas pessoas, webcam em cima + gameplay embaixo, fundo desfocado, zoom que segue o cursor em tutoriais. Use SEMPRE que o destino for Shorts/Reels/TikTok, quando o video de entrada nao for 9:16, ou quando o usuario falar em "vertical", "enquadrar", "recortar", "formato celular" ou "seguir o rosto".
---

# reframe-layouts

Escolha o layout a partir do `type` do plano e do que aparece nos frames. Grave a escolha em `clips[].layout`.

## Escolha do layout

| Situacao | Layout | Observacao |
|---|---|---|
| Uma pessoa falando, rosto grande | `face_track` | acompanha o rosto com suavizacao |
| Duas pessoas, troca rapida | `split_2` | cada uma em metade da tela |
| Duas pessoas, falante alternando | `face_track` no falante ativo | so troque de pessoa em corte seco |
| Gameplay com webcam | `gameplay_facecam` | webcam em cima, jogo embaixo |
| Gameplay sem webcam / video sem foco claro | `blur_fit` | video inteiro no meio, fundo desfocado |
| Acao concentrada no centro | `center_crop` | ajuste o deslocamento X (0 a 1) |
| Tutorial/tela | `screen_cursor` | zoom na regiao ativa seguindo o cursor |

## Receitas FFmpeg testadas (entrada 1920x1080 -> saida 1080x1920)

**center_crop** (troque `0.5` para deslocar: 0=esquerda, 1=direita):
```
ffmpeg -i in.mp4 -vf "crop=ih*9/16:ih:(iw-ih*9/16)*0.5:0,scale=1080:1920" -c:v libx264 -pix_fmt yuv420p out.mp4
```

**blur_fit** (video inteiro centralizado, fundo desfocado do proprio video):
```
ffmpeg -i in.mp4 -filter_complex "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=40:20[bg];[0:v]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2[v]" -map "[v]" -map 0:a? ...
```

**gameplay_facecam** (webcam 640x360 no canto superior direito do original; ajuste `crop=W:H:X:Y` para a posicao real da webcam; 608 + 1312 = 1920):
```
-filter_complex "[0:v]crop=640:360:1280:0,scale=1080:608[cam];[0:v]crop=ih*1080/1312:ih:(iw-ih*1080/1312)/2:0,scale=1080:1312[game];[cam][game]vstack=inputs=2[v]"
```
Olhe um frame antes para achar a webcam e o HUD do jogo; o recorte do jogo nao pode cortar vida, mira ou placar.

**split_2** (duas pessoas lado a lado no original, uma em cada metade):
```
-filter_complex "[0:v]crop=iw/2:ih:0:0,scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[a];[0:v]crop=iw/2:ih:iw/2:0,scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[b];[a][b]vstack[v]"
```

## face_track e screen_cursor (precisam de codigo)

Implemente em Python (`work/reframe.py`) com **MediaPipe** (Python 3.11/3.12 no Windows) ou OpenCV:
1. Amostre o video a 5-10 fps, detecte o rosto (ou o cursor/atividade) e guarde o centro X por tempo.
2. **Suavize** a trajetoria (media movel exponencial ou filtro de Kalman) e use **zona morta**: so mova a camera se o alvo sair de ~15% do centro. Camera tremendo e o erro mais comum.
3. Limite a velocidade de movimento; mudancas bruscas so em **cortes de cena** (detecte com PySceneDetect e reinicie o rastreio em cada corte; nunca faca pan atravessando um corte).
4. Gere a janela de recorte por frame e aplique com FFmpeg (crop com expressao por segmentos) ou renderize via OpenCV + FFmpeg para juntar o audio.
5. Se nao achar rosto por mais de ~1 s, mantenha a ultima posicao boa ou volte ao `blur_fit`.
6. Falante ativo: com WhisperX diarizacao (ou volume por canal), cruze quem fala com a posicao de cada rosto.

## Areas seguras (heuristica)
Interfaces das plataformas cobrem partes da tela. Mantenha rosto, texto e HUD importantes longe de: ~10% do topo, ~20-25% de baixo (legenda da plataforma, botoes) e a borda direita. A legenda animada fica no terco inferior, acima dessa faixa. Teste com `extract_frames.py` e confira visualmente.

## Checklist
- [ ] O assunto principal esta inteiro e legivel no celular?
- [ ] Nenhum movimento de camera atravessa um corte?
- [ ] Texto/HUD importantes nao foram cortados?
- [ ] Resolucao final 1080x1920, pixels quadrados, `yuv420p`?
