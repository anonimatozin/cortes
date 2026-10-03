---
name: hook-engine
description: Projeta e aplica o gancho (hook) dos primeiros 5 segundos de cada clipe ou video - escolhe a frase de abertura, o texto na tela, a mudanca visual inicial e o som. Use SEMPRE que for criar short/reel/tiktok, quando o usuario falar em "gancho", "prender atencao", "primeiros segundos", "retencao", "viral", ou quando um clipe comecar com enrolacao, saudacao longa, tela parada ou carregando.
---

# hook-engine

O espectador decide em poucos segundos se fica. Regra do bot: **nenhum clipe comeca sem gancho avaliado.** (Os numeros de retencao que circulam na internet sao regras praticas, nao ciencia exata: meça com os dados do canal quando existirem.)

## Linha do tempo dos primeiros 5 s

| Tempo | O que precisa acontecer |
|---|---|
| 0.0-0.5 s | Algo visual ou sonoro **muda** (corte, zoom, flash, movimento, som). Nada de tela preta, logo ou fade longo. |
| 0.5-1.5 s | A promessa/pergunta/afirmacao forte (falada e, se ajudar, escrita na tela). |
| 1.5-3 s | Prova ou contexto visual minimo (o resultado, o objeto, a reacao). |
| 3-5 s | Um "loop aberto": o espectador quer saber o desfecho. Nao entregue o payoff ainda. |

## Procedimento (para cada clipe)

1. **Leia a transcricao do clipe** e liste de 3 a 5 candidatos a abertura. Veja os tipos em `references/hook-patterns.md`.
2. **Pontue** cada candidato de 0 a 10 em: clareza (entende em 2 s), curiosidade, relevancia para o publico-alvo, e **honestidade** (o video entrega o que o gancho promete). Honestidade abaixo de 7 = descarte.
3. **Escolha o vencedor** e decida a tecnica:
   - **Comecar no melhor ponto real**: mova `clip.start` para o inicio da frase forte (mais simples e mais seguro).
   - **Cold open / teaser**: copie 1-3 s da melhor frase do clipe para o inicio e depois siga do comeco do clipe. So use se a frase nao ficar repetida de forma estranha e se o video continuar verdadeiro. Registre em `hook.reorder`.
   - **Texto de abertura**: `hook.text_on_screen` com no maximo 7 palavras, legivel por 1-1.5 s, nunca repetindo palavra por palavra a legenda.
4. **Remova a enrolacao**: corte "oi gente", "entao", "bom", apresentacao longa, silencio inicial e qualquer ruido de comeco de gravacao. A primeira palavra audivel deve estar em ate 0.3 s do inicio.
5. **Planeje a mudanca visual inicial** para a skill `motion-and-broll`: um punch-in, flash ou corte para o ponto mais interessante em 0-0.5 s. Em gameplay, comece no momento de tensao/resultado.
6. **Planeje o som:** um SFX curto (whoosh/impact) no primeiro corte e voz sem queda de volume no inicio (skill `audio-polish`).
7. Grave tudo em `clips[].hook` (type, spoken, text_on_screen, reorder, score) e o motivo em `why`.

## Proibido

- Prometer o que o video nao mostra (clickbait que frustra gera abandono e prejudica o canal).
- Abrir com logo, vinheta, "se inscreva" ou pedido de curtida.
- Comecar com imagem estatica de talking head sem movimento nem texto.
- Inventar numeros, resultados ou citacoes.

## Checagem final do hook

Depois do render (skill `render-and-verify`), olhe os frames de 0 s a 5 s e responda: *se eu visse isso no feed, pararia? O que muda no primeiro meio segundo? A promessa e clara sem som?* Se alguma resposta for "nao", volte ao passo 3.
