---
name: publish-metadata
description: Gera titulo, descricao, hashtags e tags para YouTube, TikTok e Reels de cada clipe, pesquisa hashtags em alta de forma legitima e prepara (com aprovacao humana) a divulgacao do canal numa Pagina do Facebook. Use SEMPRE que os clipes estiverem prontos, e quando o usuario pedir "titulo", "descricao", "hashtags", "tags", "legenda do post", "divulgar o canal", "postar no Facebook" ou "agendar".
---

# publish-metadata

Gere o **pacote de publicacao** de cada clipe e so publique com **aprovacao explicita do usuario**.

## 1. Pacote por clipe (`renders/<id>.publish.json`)
```json
{
  "id": "c01",
  "youtube": {"title": "...", "description": "...", "hashtags": ["#..."], "tags": ["..."]},
  "tiktok":  {"caption": "...", "hashtags": ["#..."]},
  "reels":   {"caption": "...", "hashtags": ["#..."]},
  "facebook_page": {"message": "...", "link": "https://youtube.com/..."}
}
```

## 2. Regras de texto
- **Titulo:** claro e honesto, com a palavra-chave do assunto cedo, ate ~60-70 caracteres para nao cortar; sem CAIXA ALTA inteira nem promessa falsa. Use o mesmo gancho do video (`hook-engine`), sem entregar o final.
- **Descricao:** primeira linha = o que o video entrega + palavra-chave; depois contexto curto, link do canal/video completo, creditos (musica, B-roll) quando exigido. Capitulos com tempos se for video longo.
- **Legenda do post (TikTok/Reels):** primeira frase e o gancho; uma pergunta ou chamada para comentar; hashtags no fim.
- Idioma: o do publico (pt-BR por padrao). Nada de informacao que o video nao sustenta.

## 3. Hashtags e tags
- Quantidade enxuta: **3 a 5 hashtags relevantes** por post (misture 1 ampla, 2 de nicho, 1 de tendencia SO se combinar com o conteudo). Hashtag de tendencia nao relacionada e spam e prejudica.
- Fontes legitimas de tendencia: o **TikTok Creative Center** (paginas publicas de hashtags por regiao e periodo - consulte o site; sem login mostra so uma amostra), a barra de busca/sugestao de cada plataforma e os videos de canais do mesmo nicho. APIs oficiais de analise de hashtag exigem aprovacao do app. **Nao** faca scraping que viole os termos de uso nem peca ao usuario senhas.
- **YouTube:** coloque hashtags na descricao (as primeiras aparecem acima do titulo; nao exagere). O campo "tags" tem peso pequeno para descoberta - use poucas, com variacoes de grafia/termo. Confira as regras atuais no YouTube Studio.
- Registre de onde veio cada hashtag e a data da pesquisa; tendencia vence rapido.

## 4. Divulgar o canal no Facebook (apenas Pagina)
Fatos que valem para qualquer implementacao:
- Pela API oficial (Graph API) da para publicar **numa Pagina que o usuario administra**. Perfil pessoal nao e possivel, e publicar em Grupos esta, na pratica, fechado para apps novos.
- Para postar video em Pagina o app precisa das permissoes `pages_show_list`, `pages_read_engagement`, `pages_manage_posts` e, para video, `publish_video`, todas sujeitas a **App Review** da Meta, com token de acesso da Pagina.
- Antes de escrever codigo, **leia a documentacao atual** (developers.facebook.com, secoes Pages API e Video API): endpoints e hosts de upload mudam (o host antigo de upload de video foi descontinuado em favor do Resumable Upload API).

Boas praticas obrigatorias do bot:
1. **Modo `--dry-run` por padrao:** mostra o que seria postado e nao posta.
2. **Aprovacao humana** antes de cada postagem (ou lote). Nada de postar sozinho.
3. Tokens e segredos em variaveis de ambiente / arquivo `.env` fora do Git. Jamais no codigo, em logs ou no chat.
4. **Frequencia moderada** (nao inunde a Pagina) e variacao de texto; sem repetir o mesmo post. Respeite limites da API e trate erros (token expirado, permissao negada).
5. Agendar: a API aceita post agendado dentro de uma janela (de ~10 min a ~30 dias adiante). Confirme na documentacao atual.
6. O texto leva o link do canal/video e uma razao para clicar; o video postado e o corte, nao o link solto.

Se o usuario ainda nao tem o app aprovado, entregue so o pacote de texto e um passo a passo para ele publicar manualmente na Pagina, e avise que a aprovacao da Meta pode levar tempo.

## 5. Entrega
Mostre uma tabela (clipe, titulo, hashtags) e pergunte o que aprovar. Atualize `renders/<id>.publish.json`.
