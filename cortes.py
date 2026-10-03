import argparse
import atexit
import json
import os
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from core import analyze, art, captions, config, editor, fetch, render, research, select, shopee, store, transcribe
from core.config import CLIPS_DIR, QUEUE_DIR, SOURCE_DIR


def _dedupe_tags(tags):
    seen, out = set(), []
    for t in tags:
        t = (t or "").strip()
        key = t.lower()
        if t and key not in seen:
            seen.add(key)
            out.append(t)
    return out[:30]


def compose_tiktok_caption(clip, limit=2100):
    txt = (clip.get("legenda_tiktok") or
           f"{clip.get('title', '')}\n\n{clip.get('description', '')}").strip()
    hashtags = research.clean_hashtags(clip.get("hashtags") or ["#cortes"], config.HASHTAGS_MAX)
    existing = {token.lower() for token in txt.split() if token.startswith("#")}
    missing = [tag for tag in hashtags if tag.lower() not in existing]
    if missing:
        txt = f"{txt}\n\n{' '.join(missing)}".strip()
    if len(txt) > limit:
        txt = txt[:limit].rsplit(" ", 1)[0]
    return txt


def _shopee_block(title, desc, hashtags=None):
    if not shopee.on():
        return ""
    try:
        kw = [str(h).lstrip("#") for h in (hashtags or []) if h]
        item = shopee.pick_for_video(title, desc, keywords=kw)
        return shopee.block(item)
    except Exception as exc:
        log(f"  [shopee] pulou: {exc}")
        return ""


def _trocar_hashtags(texto, novas):
    novas = [str(h) for h in (novas or []) if h]
    if not novas:
        return texto or ""
    out, trocou = [], False
    for ln in (texto or "").splitlines():
        s = ln.strip()
        toks = s.split()
        if s.startswith("#") and toks and all(t.startswith("#") for t in toks):
            if not trocou:
                out.append(" ".join(novas))
                trocou = True
            continue
        out.append(ln)
    if not trocou:
        if out and out[-1]:
            out.append("")
        out.append(" ".join(novas))
    return "\n".join(out)


def _divulgacao_meta(clip):
    try:
        from divulgacao import hashtags as _dh
        return _dh.carregar_metadata(Path(clip["path"]).stem)
    except Exception:
        return None


def _gerar_divulgacao(clip, job):
    try:
        from divulgacao.integracao import apos_exportacao
        apos_exportacao(clip, job=job, on_log=log)
    except Exception as exc:
        log(f"  [divulgacao] pulou: {exc}")


def _youtube_meta(edit, ai, ctx, meta, clip_text=""):
    title = editor.best_title(
        edit, ai, clip_text or (edit or {}).get("descricao") or ai.get("description", "")
    )
    desc = ((edit or {}).get("descricao") or "").strip() or (ai.get("description") or "").strip()
    hashtags = research.clean_hashtags(
        (edit or {}).get("hashtags") or ai.get("hashtags") or ["#cortes", "#shorts"], config.HASHTAGS_MAX
    )
    parts = [desc]
    if hashtags:
        parts.append(" ".join(hashtags))
    if config.CREDITS_STYLE != "off":
        parts.append(research.credit_block(ctx, config.CREDITS_STYLE).strip("\n"))
    promo = _shopee_block(title, desc, hashtags)
    if promo:
        parts.append(promo)
    base = editor.all_tags(edit) or (ai.get("tags") or [])
    base = research.clean_tags(base + [meta.get("channel") or "", "cortes", "shorts"], 24)
    tags = _dedupe_tags(base)
    return title, "\n\n".join(p for p in parts if p), hashtags, tags


def _short_credit(ctx):
    if config.CREDITS_STYLE == "off":
        return ""
    return research.credit_block(ctx, "full").strip()


def _platform_text(edit, ai, ctx, limit=1500, with_hook=False):
    parts = []
    if with_hook and ai.get("hook"):
        parts.append(str(ai["hook"]).upper().strip())
    titulos = (edit or {}).get("titulos") or []
    if titulos:
        parts.append(titulos[0].strip())
    desc = ((edit or {}).get("descricao") or (ai.get("description") or "")).strip()
    if desc:
        parts.append(desc)
    tags = research.clean_hashtags(
        (edit or {}).get("hashtags") or ai.get("hashtags"), config.HASHTAGS_MAX
    )
    if tags:
        parts.append(" ".join(tags))
    credit = _short_credit(ctx)
    if credit:
        parts.append(credit)
    promo = _shopee_block(titulos[0] if titulos else (ai.get("title") or ""), desc, tags)
    if promo:
        parts.append(promo)
    txt = "\n\n".join(p for p in parts if p)
    if len(txt) > limit:
        txt = txt[:limit].rsplit(" ", 1)[0]
    return txt


def _tiktok_text(edit, ai, ctx):
    return _platform_text(edit, ai, ctx, limit=2100)


def _reels_text(edit, ai, ctx):
    return _platform_text(edit, ai, ctx, limit=2000, with_hook=True)


def log(msg):
    print(msg, flush=True)


def _transcript_path(video_id):
    return SOURCE_DIR / f"{video_id}.transcript.json"


def cmd_doctor(args):
    ok = True
    checks = []

    def check(name, fn):
        nonlocal ok
        try:
            detail = fn()
            checks.append(("OK ", name, detail or ""))
        except Exception as exc:
            ok = False
            checks.append(("ERRO", name, str(exc)))

    check("ffmpeg", lambda: __import__("subprocess").run(["ffmpeg", "-version"], capture_output=True, text=True).stdout.splitlines()[0])
    check("yt-dlp", lambda: __import__("yt_dlp").version.__version__)
    check("faster-whisper", lambda: __import__("faster_whisper").__version__)
    check("numpy", lambda: __import__("numpy").__version__)
    check("Groq key", lambda: config.GROQ_API_KEY and "configurada" or (_ for _ in ()).throw(RuntimeError("vazia - edite .env")))
    check("YouTube client", lambda: config.CRED_DIR.joinpath("client_secret.json").exists() and "client_secret.json" or (_ for _ in ()).throw(RuntimeError("ausente em credentials\\")))
    check("YouTube token", lambda: config.TOKENS_DIR.joinpath("youtube.json").exists() and "logado" or "falta rodar: python cortes.py auth")
    check("TikTok app", lambda: (config.TIKTOK_CLIENT_KEY and config.TIKTOK_CLIENT_SECRET) and "client key ok" or "nao configurado no .env")
    check("TikTok token", lambda: config.TOKENS_DIR.joinpath("tiktok.json").exists() and "logado" or "falta: python cortes.py auth --tiktok")
    check("Instagram app", lambda: (config.IG_APP_ID and config.IG_APP_SECRET) and "app id ok" or "nao configurado no .env")
    check("Instagram token", lambda: (__import__("core.instagram", fromlist=["doctor"]).doctor()
                                       if config.IG_ACCESS_TOKEN else "vazio no .env"))
    check("Shopee afiliado", lambda: (
        "API ok (AppId configurado)" if (shopee.APP_ID and shopee.SECRET)
        else (f"catalogo: {len(shopee.catalog())} link(s)" if shopee.catalog()
              else "sem API e sem catalogo -> cole seus links em queue\\shopee_catalog.txt")))

    for status, name, detail in checks:
        line = f"[{status}] {name}"
        if detail:
            line += f" -> {detail}"
        log(line)
    return 0 if ok else 1


def cmd_auth(args):
    if getattr(args, "code"):
        from core import tiktok
        tiktok.auth_with_code(args.code)
        log("TikTok autorizado (codigo colado). Token em tokens\\tiktok.json")
        return 0
    if getattr(args, "tiktok"):
        from core import tiktok
        tiktok.auth(interactive=True)
        log("TikTok autorizado. Token salvo em tokens\\tiktok.json")
        log("IMPORTANTE: os cortes vao pra Caixa de Entrada do TikTok; e la que voce publica.")
        return 0
    from core import youtube
    youtube.auth(interactive=True)
    log("YouTube autorizado. Token salvo em tokens\\youtube.json")
    return 0


def cmd_run(args):
    from core import face

    job = store.find_job_by_url(args.url) or store.new_job(args.url)
    meta = job.get("meta") or {}

    if job.get("stage") not in ("rendered", "published") or args.force or not meta.get("path"):
        log("1/6 baixando video...")
        meta = fetch.download(args.url)
        job["meta"] = meta
        job["stage"] = "downloaded"
        job["error"] = None
        store.upsert_job(job)
        log(f"     {meta['title']} ({int(meta.get('duration') or 0)}s)")
    else:
        meta = job["meta"]
        log(f"1/6 ja baixado: {meta['title']}")

    source = Path(meta["path"])
    duration = float(meta.get("duration") or 0) or _duration(source)

    tpath = _transcript_path(meta["id"])
    if tpath.exists() and not args.force:
        log("2/6 transcricao ja existe")
        transcript = json.loads(tpath.read_text(encoding="utf-8"))
    else:
        log("2/6 transcrevendo (whisper)...")
        transcript = transcribe.transcribe(str(source), str(tpath), language=getattr(args, "lang", None))
        log(f"     {len(transcript['words'])} palavras")

    words, segments = transcript["words"], transcript["segments"]
    if not words:
        raise RuntimeError("transcricao vazia")

    log("3/6 analisando audio...")
    rms = analyze.envelope(str(source))
    candidates = analyze.build_candidates(words, segments, rms, duration)
    candidates = analyze.rank_candidates(candidates, top=40)
    log(f"     {len(candidates)} candidatos")

    if args.dry:
        for i, c in enumerate(candidates):
            log(f"  [{i}] {c['start']:7.1f} -> {c['end']:7.1f}  energia={c['energy']:.3f} pre={c['pre_score']}")
            log(f"        {c['text'][:160]}")
        return 0

    log("4/6 IA escolhendo os melhores cortes...")
    ctx = research.build_context(meta)
    if ctx["related"]:
        log(f"     pesquisa: {len(ctx['related'])} videos parecidos, {len(ctx['tags'])} tags do autor")
    limit = args.clips or config.CLIPS_PER_VIDEO
    chosen = select.select_best(candidates, ctx, limit, on_progress=log)
    if not chosen:
        raise RuntimeError("nenhum corte aprovado pela IA")
    log(f"     {len(chosen)} cortes aprovados")

    log("5/6 renderizando em 9:16 com legendas...")
    clips = []
    for i, c in enumerate(chosen, start=1):
        ai = c["ai"]
        c_start = c["start"]
        primeiro = next((w for w in words if w["end"] > c_start), None)
        if (primeiro and primeiro["start"] - c_start >= 0.6
                and c["end"] - (primeiro["start"] - 0.15) >= 20):
            log(f"     [{i}] gancho: cortando {primeiro['start'] - c_start:.1f}s de silencio no inicio")
            c_start = max(c_start, primeiro["start"] - 0.15)
        edit = editor.plan(c.get("text", ""), c["end"] - c_start, ctx, hint=ai.get("hook", ""))
        if edit:
            sec = f" (+{', '.join(edit['tipos_secundarios'])})" if edit["tipos_secundarios"] else ""
            log(f"     [{i}] tipo={edit['tipo']}{sec} dinamismo={edit['dinamismo']}")
            log(f"         edicao: {edit['edicao']['cortes'][:110]}")
        zoom, push, cap_size = editor.motion_profile(edit, c.get("text", ""))
        slug = (
            ai.get("hook")
            or             ai.get("title")
            or " ".join((c.get("text") or "").split()[:6])
            or f"corte_{i}"
        )
        out = render.clip_filename(i, slug, source.stem)
        reframe = None
        if config.REFRAME and not args.no_reframe:
            reframe = face.focus_for_clip(source, c_start, c["end"])
            if not reframe["found"]:
                reframe = None
            else:
                log(f"     [{i}] rosto fx={reframe['fx']:.2f} fy={reframe['fy']:.2f} "
                    f"tamanho={reframe['fh']:.2f} ({reframe['samples']} amostras)")
        if out.exists() and not args.force:
            c_start = c["start"]
            log(f"     [{i}] ja renderizado {out.name}")
            info = {"path": str(out), "duration": round(c["end"] - c["start"], 2), "size": out.stat().st_size}
            overlays = []
        else:
            overlays = []
            if config.IMAGES_ENABLED and not args.no_images:
                visuals = art.plan_visuals(
                    c.get("text", ""), c["end"] - c_start, ai.get("hook", "")
                )
                if visuals:
                    log(f"     [{i}] {len(visuals)} imagem(ns) de IA planejada(s)")
                    overlays = art.prepare(i, out, visuals)
            words_cap = words
            lang = str(transcript.get("language") or "").lower()
            if lang and not lang.startswith(("pt", "portug")):
                words_cap = captions.traduzir_words(
                    words, c_start, c["end"],
                    f"{source.stem}_{int(c_start * 10)}", on_log=log,
                )
            info = render.render_clip(
                source, c_start, c["end"], out, words_cap,
                hook=ai.get("hook", ""), crop_focus=args.focus,
                reframe=reframe, overlays=overlays,
                zoom=zoom, push=push, caption_size=cap_size,
            )
            log(f"     [{i}] {out.name}  {info['duration']}s  {info['size'] // 1024}KB")
        verif = _verificar_render(out, on_log=log)
        if verif["falhas"]:
            log(f"     [{i}] verificacao REPROVOU: {' | '.join(verif['falhas'])[:220]}")
        elif verif["avisos"]:
            log(f"     [{i}] verificacao: {len(verif['avisos'])} aviso(s)")
        title, description, hashtags, tags = _youtube_meta(edit, ai, ctx, meta, c.get("text", ""))
        clip = {
            "index": i,
            "path": info["path"],
            "start": round(c_start, 3),
            "end": round(c["end"], 3),
            "duration": info["duration"],
            "size": info["size"],
            "score": ai.get("score", 0),
            "hook": ai.get("hook", ""),
            "title": title[:100],
            "description": description,
            "hashtags": hashtags,
            "tags": tags,
            "status": "ready",
            "youtube": None,
            "tiktok": None,
            "reframe": ({k: v for k, v in reframe.items() if k != "track"} if reframe else None),
            "edit": edit,
            "legenda_tiktok": _tiktok_text(edit, ai, ctx),
            "legenda_reels": _reels_text(edit, ai, ctx),
            "visuals": [
                {"start": o["start"], "end": o["end"], "pos": o["pos"], "prompt": o["prompt"]}
                for o in overlays
            ],
            "verify": verif,
        }
        if not verif["passed"]:
            clip["bloqueado"] = True
            log(f"     [{i}] clipe bloqueado (nao publica; re-renderize com --force)")
        render.write_sidecar(info["path"], clip)
        _gerar_divulgacao(clip, job)
        clips.append(clip)

    job["clips"] = clips
    job["stage"] = "rendered"
    store.upsert_job(job)
    log(f"6/6 prontos em {CLIPS_DIR}")

    if args.publish:
        return cmd_publish(argparse.Namespace(limit=None, job=job["id"], privacy=args.privacy, platform="youtube"))
    log("use: python cortes.py publish")
    return 0


VERIFY_SKILL = Path(__file__).resolve().parent / ".claude" / "skills" / "render-and-verify" / "scripts" / "verify_render.py"


def _parse_verify(stdout, returncode):
    falhas, avisos = [], []
    for raw in (stdout or "").splitlines():
        line = raw.strip()
        if line.startswith("[FALHA]"):
            falhas.append(line[len("[FALHA]"):].strip())
        elif line.startswith("[AVISO]"):
            avisos.append(line[len("[AVISO]"):].strip())
    return {"passed": returncode == 0, "falhas": falhas, "avisos": avisos}


def _verificar_render(out, on_log=log):
    """Skill render-and-verify: checagem tecnica do clipe (resolucao, duracao, audio, loudness, preto/congelado)."""
    if not VERIFY_SKILL.exists():
        return {"passed": True, "falhas": [], "avisos": []}
    import subprocess

    cmd = [
        sys.executable, str(VERIFY_SKILL), str(out),
        "--width", str(config.VIDEO_WIDTH), "--height", str(config.VIDEO_HEIGHT),
        "--fps", "30", "--min-dur", "15", "--max-dur", "65",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=180)
    except Exception as exc:
        on_log(f"     verificacao nao rodou: {exc}")
        return {"passed": True, "falhas": [], "avisos": []}
    verif = _parse_verify(proc.stdout, proc.returncode)
    if proc.returncode and not verif["falhas"]:
        ultima = ((proc.stderr or proc.stdout or "").strip().splitlines() or [""])[-1]
        verif["falhas"].append(f"verify rc={proc.returncode} {ultima}".strip())
    return verif


def _lock_publicacao():
    """Evita que duas tarefas agendadas publiquem ao mesmo tempo."""
    lock = QUEUE_DIR / "publish.lock"
    for _ in range(2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                idade = time.time() - lock.stat().st_mtime
            except OSError:
                continue
            if idade < 45 * 60:
                log(f"outra publicacao em andamento ({int(idade)}s); esta tentativa foi pulada")
                return None
            log(f"lock antigo ({int(idade)}s) da publicacao anterior; assumindo")
            try:
                lock.unlink()
            except OSError:
                return None
            continue
        with os.fdopen(fd, "w") as fh:
            fh.write(str(os.getpid()))
        atexit.register(lambda: lock.unlink(missing_ok=True))
        return lock
    return None


def cmd_publish(args):
    if _lock_publicacao() is None:
        return 0
    from core import tiktok, youtube

    platform = getattr(args, "platform", None) or "youtube"
    targets = ["youtube", "tiktok", "instagram"] if platform == "ambos" else [platform]

    data = store.load_jobs()
    jobs = data["jobs"]
    if getattr(args, "job", None):
        jobs = [j for j in jobs if j["id"] == args.job]

    pending = []
    for j in jobs:
        for c in j.get("clips", []):
            if not Path(c["path"]).exists():
                continue
            if c.get("bloqueado"):
                continue
            if getattr(args, "from_youtube", False) and not c.get("youtube"):
                continue
            if c.get("status") == "ready" or any(not c.get(t) for t in targets):
                pending.append((j, c))
    por_fonte = {}
    for item in pending:
        por_fonte.setdefault(item[0].get("meta", {}).get("id") or item[0]["id"], []).append(item)
    for fila in por_fonte.values():
        fila.sort(key=lambda x: x[1].get("score", 0), reverse=True)
    prioridade = [k for k in config.FONTE_PRIORIDADE if k in por_fonte]
    resto = sorted(
        [k for k in por_fonte if k not in prioridade],
        key=lambda k: por_fonte[k][0][1].get("score", 0),
        reverse=True,
    )

    def _inter(keys):
        out = []
        while any(por_fonte[k] for k in keys):
            for k in keys:
                if por_fonte[k]:
                    out.append(por_fonte[k].pop(0))
        return out

    pending = _inter(prioridade) + _inter(resto)

    if not pending:
        log("nenhum corte pendente de upload")
        return 0

    yt_left = youtube.quota_left() if "youtube" in targets else None
    log(f"{len(pending)} corte(s) na fila" + (f" | contador local ~{yt_left} (estimativa)" if yt_left is not None else ""))
    done = 0
    quota_hit = False
    ultimo_yt = 0.0
    for job, clip in pending:
        if quota_hit:
            break
        if args.limit and done >= args.limit:
            break
        missing = [t for t in targets if not clip.get(t)]
        if "tiktok" in missing and clip.get("sem_tiktok"):
            missing = [t for t in missing if t != "tiktok"]
        if not missing:
            continue

        tk_direto = "tiktok" in missing and config.TIKTOK_MODE in ("auto", "direct") and tiktok.can_direct()
        if "tiktok" in missing and not tk_direto and _pending("tiktok") >= config.TIKTOK_PENDING_CAP:
            log(f"limite de {config.TIKTOK_PENDING_CAP} rascunhos pendentes do TikTok em 24h, pulando")
            missing = [t for t in missing if t != "tiktok"]
        if "instagram" in missing and _pending("instagram") >= 100:
            log("limite de 100 posts/24h do Instagram atingido, pulando")
            missing = [t for t in missing if t != "instagram"]
        if not missing:
            continue

        dm = _divulgacao_meta(clip)
        yt_title, yt_desc, yt_tags = clip["title"], clip["description"], clip["tags"]
        tt_cap = compose_tiktok_caption(clip)
        if dm:
            yt_title = str(dm.get("titulo") or clip["title"])[:100]
            yt_desc = _trocar_hashtags(dm.get("descricao") or clip["description"], dm.get("hashtags"))
            yt_tags = _dedupe_tags(dm.get("tags_youtube_lista") or clip["tags"])
            tt_cap = _trocar_hashtags(tt_cap, dm.get("hashtags_tiktok") or dm.get("hashtags"))
            log(f"  [divulgacao] {len(dm.get('hashtags') or [])} hashtags, "
                f"{len(dm.get('tags_youtube_lista') or [])} tags do YouTube")
        log(f"enviando: {yt_title} -> {', '.join(missing)}")
        ok_one = False
        for p in missing:
            try:
                if p == "youtube" and ultimo_yt:
                    espera = 120 - (time.time() - ultimo_yt)
                    if espera > 0:
                        log(f"  esperando {int(espera)}s para espacar os uploads do YouTube")
                        time.sleep(espera)
                if p == "youtube":
                    res = youtube.upload(
                        clip["path"], yt_title, yt_desc, yt_tags,
                        privacy=args.privacy or config.PRIVACY,
                    )
                    res = {"id": res["id"], "url": res["url"], "title": res["title"],
                           "privacy": args.privacy or config.PRIVACY}
                elif p == "instagram":
                    from core import instagram
                    r = instagram.publish(
                        clip["path"],
                        clip.get("legenda_reels") or clip.get("description", ""),
                        on_progress=log,
                    )
                    res = {"id": r["id"], "url": r.get("url", ""), "title": clip["title"],
                           "privacy": "public"}
                else:
                    from core import tiktok
                    cap = tt_cap
                    modo = config.TIKTOK_MODE
                    if modo in ("auto", "direct") and tiktok.can_direct():
                        r = tiktok.upload_direct(clip["path"], cap, on_progress=log)
                        res = {"id": r["publish_id"], "url": "", "title": clip["title"],
                               "caption": cap, "status": r.get("status", ""), "mode": "direct"}
                    else:
                        if modo == "direct":
                            log("  Direct Post pedido mas sem escopo video.publish -> inbox")
                        r = tiktok.upload_draft(clip["path"], on_progress=log)
                        res = {"id": r["publish_id"], "url": "", "title": clip["title"],
                               "caption": cap, "status": r.get("status", ""), "mode": "inbox"}
                        log("  TikTok Upload enviou um rascunho para a caixa de entrada; "
                            "ele só terá views depois de publicar no app.")
            except youtube.QuotaError as exc:
                log(f"  {exc}")
                log("cota real do YouTube atingida, parando aqui")
                store.upsert_job(job)
                quota_hit = True
                break
            except Exception as exc:
                log(f"  FALHOU {p}: {exc}")
                clip.setdefault("errors", {})[p] = str(exc)[:300]
                store.upsert_job(job)
                continue
            clip[p] = res
            if p == "youtube":
                ultimo_yt = time.time()
            ok_one = True
            store.add_upload({
                "id": res["id"],
                "platform": p,
                "url": res.get("url", ""),
                "title": res["title"],
                "job": job.get("id"),
                "clip_index": clip.get("index"),
                "privacy": res.get("privacy", "inbox"),
                "uploaded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            log(f"  OK [{p}] {res.get('url') or ('rascunho no TikTok' if p == 'tiktok' else 'publicado')}")

        if ok_one:
            clip.setdefault("published_at", time.strftime("%Y-%m-%d %H:%M:%S"))
            alvo = [t for t in targets if not (t == "tiktok" and clip.get("sem_tiktok"))]
            if all(clip.get(t) for t in alvo):
                clip["status"] = "published"
            clip.pop("errors", None)
            store.upsert_job(job)
            done += 1
            tt = clip.get("tiktok")
            if tt and tt.get("caption") and tt.get("mode") != "direct":
                log("  legenda do TikTok (cola no app):")
                for line in tt["caption"].splitlines():
                    log(f"    {line}")
    log(f"{done} corte(s) enviado(s)")
    if quota_hit:
        log("restante fica pra quando a cota do YouTube zerar")
    return 0


def _pending(platform, hours=24):
    limit = time.time() - hours * 3600
    n = 0
    for u in store.load_uploads():
        if u.get("platform") != platform:
            continue
        ts = u.get("uploaded_at", "")
        try:
            if time.mktime(time.strptime(ts, "%Y-%m-%d %H:%M:%S")) >= limit:
                n += 1
        except ValueError:
            n += 1
    return n


def _tiktok_pending():
    return _pending("tiktok")


def cmd_purge(args):
    from core import instagram, youtube

    recs = store.load_uploads()
    if args.id:
        wanted = set(args.id)
        recs = [u for u in recs if u.get("id") in wanted and not u.get("deleted")]
    else:
        recs = [u for u in recs
                if not u.get("deleted") and u.get("platform", "youtube") in ("youtube", "instagram")]
    if not recs:
        log("nenhum video registrado para excluir")
        return 0

    data = store.load_jobs()
    for u in recs:
        vid, plat = u["id"], u.get("platform", "youtube")
        log(f"excluindo [{plat}] {vid}...")
        try:
            if plat == "instagram":
                instagram.delete(vid)
            else:
                youtube.delete(vid)
        except Exception as exc:
            log(f"  FALHOU: {exc}")
            continue
        store.mark_deleted(vid)
        for j in data["jobs"]:
            for c in j.get("clips", []):
                if (c.get(plat) or {}).get("id") == vid:
                    c["status"] = "ready"
                    c[plat] = None
                    c.pop("published_at", None)
                    store.upsert_job(j)
        log("  ok")
    return 0


def cmd_privacy(args):
    from core import youtube

    status = args.status
    items = store.load_uploads()
    recs = [u for u in items
            if not u.get("deleted") and u.get("platform", "youtube") == "youtube"]
    if args.id:
        wanted = set(args.id)
        recs = [u for u in recs if u.get("id") in wanted]
    else:
        recs = [u for u in recs if u.get("privacy") != status]
    if not recs:
        log(f"nada para mudar (ja {status})")
        return 0

    log(f"{len(recs)} video(s) -> {status}")
    for u in recs:
        try:
            youtube.set_privacy(u["id"], status)
        except Exception as exc:
            log(f"  FALHOU {u['id']}: {exc}")
            if "quota" in str(exc).lower() or "limit" in str(exc).lower():
                log("  cota do YouTube atingida, parando")
                break
            continue
        u["privacy"] = status
        log(f"  {u['id']} -> {status}")
    store.save_uploads(items)
    return 0


def cmd_list(args):
    data = store.load_jobs()
    if not data["jobs"]:
        log("vazio")
        return 0
    for j in data["jobs"]:
        meta = j.get("meta") or {}
        log(f"[{j['id']}] {j['stage']:<10} {meta.get('title','')}")
        for c in j.get("clips", []):
            log(f"    {c['index']}. {c['status']:<10} {c.get('score',''):>3} {c['title']}")
    return 0


def cmd_clip(args):
    from core import face

    src = Path(args.source)
    words = json.loads((SOURCE_DIR / f"{src.stem}.transcript.json").read_text(encoding="utf-8"))["words"]
    out = CLIPS_DIR / args.out if args.out else render.clip_filename(1, src.stem)
    reframe = None if args.no_reframe else face.focus_for_clip(src, args.start, args.end)
    if reframe and not reframe["found"]:
        reframe = None
    if reframe:
        log(f"rosto fx={reframe['fx']:.2f} fy={reframe['fy']:.2f} fh={reframe['fh']:.2f}")
    info = render.render_clip(src, args.start, args.end, out, words, hook=args.hook,
                              crop_focus=args.focus, reframe=reframe)
    log(f"{info['path']} {info['duration']}s")
    return 0


def _duration(path):
    import subprocess
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return float(r.stdout.strip() or 0)


def main():
    p = argparse.ArgumentParser(prog="cortes", description="Pipeline de cortes automaticos 9:16")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="checa dependencias e credenciais")
    a = sub.add_parser("auth", help="login OAuth (YouTube ou TikTok)")
    a.add_argument("--tiktok", action="store_true", help="autoriza o TikTok em vez do YouTube")
    a.add_argument("--code", default=None, help="codigo ?code= colado manualmente do TikTok")
    sub.add_parser("list", help="lista trabalhos e cortes")

    r = sub.add_parser("run", help="baixa, transcreve, escolhe e renderiza")
    r.add_argument("url")
    r.add_argument("--clips", type=int, default=None)
    r.add_argument("--publish", action="store_true")
    r.add_argument("--privacy", default=None, choices=["private", "unlisted", "public"])
    r.add_argument("--focus", type=float, default=0.5, help="0=esquerda 0.5=centro 1=direita")
    r.add_argument("--force", action="store_true")
    r.add_argument("--dry", action="store_true", help="so mostra candidatos")
    r.add_argument("--no-reframe", action="store_true", help="desliga foco automatico no rosto")
    r.add_argument("--no-images", action="store_true", help="desliga imagens de IA")
    r.add_argument("--lang", default=None, choices=["auto", "pt", "en"],
                   help="idioma da transcricao (auto=detecta; padrao=LANGUAGE do .env)")

    b = sub.add_parser("publish", help="envia cortes prontos")
    b.add_argument("--limit", type=int, default=None)
    b.add_argument("--job", default=None)
    b.add_argument("--privacy", default=None, choices=["private", "unlisted", "public"])
    b.add_argument("--platform", default="youtube", choices=["youtube", "tiktok", "instagram", "ambos"])
    b.add_argument("--from-youtube", action="store_true", help="so cortes que ja estao no YouTube")

    g = sub.add_parser("purge", help="exclui do YouTube videos publicados pelo bot")
    g.add_argument("--id", action="append", default=[], help="video id (repetivel); sem nada exclui todos os registrados")

    v = sub.add_parser("privacy", help="muda a visibilidade de videos ja publicados")
    v.add_argument("--status", default="public", choices=["private", "unlisted", "public"])
    v.add_argument("--id", action="append", default=[], help="video id (repetivel); sem nada pega todos os registrados")

    c = sub.add_parser("clip", help="renderiza um trecho manual")
    c.add_argument("source")
    c.add_argument("start", type=float)
    c.add_argument("end", type=float)
    c.add_argument("--out", default=None)
    c.add_argument("--hook", default="")
    c.add_argument("--focus", type=float, default=0.5)
    c.add_argument("--no-reframe", action="store_true")

    args = p.parse_args()
    handler = {
        "doctor": cmd_doctor, "auth": cmd_auth, "run": cmd_run,
        "publish": cmd_publish, "list": cmd_list, "clip": cmd_clip,
        "purge": cmd_purge,
        "privacy": cmd_privacy,
    }[args.cmd]
    try:
        return handler(args)
    except KeyboardInterrupt:
        log("interrompido")
        return 130
    except Exception as exc:
        log(f"ERRO: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
