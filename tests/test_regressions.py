import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from core import analyze, art, config, editor, face, render, research, select, store, tiktok
from cortes import _parse_verify, compose_tiktok_caption


class RegressionTests(unittest.TestCase):
    def test_candidate_starts_with_first_segment_and_stays_in_duration(self):
        segments = [
            {"start": 0.0, "end": 10.0, "text": "primeiro segmento"},
            {"start": 10.0, "end": 20.0, "text": "segundo segmento"},
            {"start": 20.0, "end": 35.0, "text": "terceiro segmento"},
        ]
        candidates = analyze.build_candidates(
            words=[], segments=segments, rms=np.ones(80), duration=30.0,
            target=25.0, cap=10,
        )
        self.assertTrue(candidates)
        self.assertEqual(candidates[0]["start"], 0.0)
        self.assertLessEqual(candidates[0]["end"], 30.0)
        self.assertIn("primeiro segmento", candidates[0]["text"])

    def test_corrupt_jobs_file_falls_back_to_empty_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "jobs.json"
            path.write_text("{invalido", encoding="utf-8")
            with patch.object(store, "JOBS_PATH", path):
                self.assertEqual(store.load_jobs(), {"jobs": []})

    def test_groq_network_error_is_retried(self):
        calls = []

        def fail(*args, **kwargs):
            calls.append(1)
            raise select.requests.ConnectionError("offline")

        with patch.object(select.requests, "post", side_effect=fail), patch.object(select.time, "sleep"):
            with self.assertRaises(select.requests.ConnectionError):
                select._chat({"model": "test"}, retries=3)
        self.assertEqual(len(calls), 3)

    def test_editor_fallback_generates_relevant_metadata(self):
        plan = editor.fallback_plan(
            "O time construiu uma fábrica de diamantes e perdeu tudo no servidor.",
            42,
            {"tags": ["minecraft"]},
        )
        self.assertTrue(plan["titulos"])
        self.assertIn("diamantes", plan["descricao"])
        self.assertTrue(plan["hashtags"])
        self.assertTrue(all(h.startswith("#") and " " not in h for h in plan["hashtags"]))

    def test_title_and_credit_are_ranked_and_traceable(self):
        title = editor.best_title(
            {"titulos": ["Viral!!!", "A fábrica de diamantes destruiu o spawn"]},
            {},
            "fábrica de diamantes destruiu o spawn",
        )
        self.assertEqual(title, "A fábrica de diamantes destruiu o spawn")
        credit = research.credit_block({
            "channel": "Canal Original", "title": "Vídeo fonte", "url": "https://example.com/video"
        })
        self.assertIn("Canal Original", credit)
        self.assertIn("https://example.com/video", credit)

    def test_motion_profile_varies_by_content_type(self):
        interview = editor.motion_profile({"tipo": "Entrevista", "dinamismo": "alto"})
        meme = editor.motion_profile({"tipo": "Meme", "dinamismo": "medio"})
        self.assertLess(interview[0], meme[0])
        self.assertLess(interview[2], meme[2])

    def test_visual_fallback_uses_the_clip_subject(self):
        with patch.object(art, "GROQ_API_KEY", ""):
            visuals = art.plan_visuals(
                "O time construiu uma fábrica de diamantes no servidor.", 42, "A fábrica foi destruída"
            )
        self.assertEqual(len(visuals), 1)
        self.assertIn("fábrica de diamantes", visuals[0]["prompt"])
        self.assertGreaterEqual(visuals[0]["rel"], 2)
        self.assertLess(visuals[0]["rel"] + visuals[0]["dur"], 42)

    def test_visual_plan_avoids_overlap_and_empty_prompt(self):
        payload = {"visuals": [
            {"rel": 3, "dur": 4, "pos": "right", "prompt": "first"},
            {"rel": 3.2, "dur": 4, "pos": "left", "prompt": "overlap"},
            {"rel": 20, "dur": 3, "pos": "top", "prompt": "second"},
            {"rel": 25, "dur": 3, "pos": "right", "prompt": ""},
        ]}
        with patch.object(art, "GROQ_API_KEY", "configured"), patch.object(
            art, "IMAGES_MAX", 4
        ), patch.object(art, "_chat", return_value=json.dumps(payload)):
            visuals = art.plan_visuals("fala sobre um assunto", 35, "gancho", max_n=4)
        self.assertEqual([v["prompt"] for v in visuals], ["first", "overlap", "second"])
        for previous, current in zip(visuals, visuals[1:]):
            self.assertGreaterEqual(current["rel"], previous["rel"] + previous["dur"] + 0.5)

    def test_gemini_retries_rate_limit_and_saves_inline_image(self):
        response = Mock(status_code=200)
        response.json.return_value = {"candidates": [{"content": {"parts": [
            {"inlineData": {"data": base64.b64encode(b"png").decode()}}
        ]}}]}
        limited = Mock(status_code=429, text="busy")
        with tempfile.TemporaryDirectory() as tmp, patch.object(config, "GEMINI_API_KEY", "key"), patch(
            "requests.post", side_effect=[limited, response]
        ), patch.object(art.time, "sleep"):
            path = Path(tmp) / "image.png"
            art._gemini("draw a server", path, (1024, 1024))
            self.assertEqual(path.read_bytes(), b"png")

    def test_gemini_uses_interactions_fallback_when_legacy_endpoint_is_unavailable(self):
        legacy = Mock(status_code=404, text="not found")
        current = Mock(status_code=200)
        current.json.return_value = {"output_image": {"data": base64.b64encode(b"png2").decode()}}
        with tempfile.TemporaryDirectory() as tmp, patch.object(config, "GEMINI_API_KEY", "key"), patch(
            "requests.post", side_effect=[legacy, current]
        ) as post, patch.object(art.time, "sleep"):
            path = Path(tmp) / "image.png"
            art._gemini("draw a server", path, (1024, 1024))
            self.assertEqual(path.read_bytes(), b"png2")
            self.assertIn("interactions", post.call_args_list[-1].args[0])

    def test_tiktok_caption_includes_relevant_hashtags(self):
        caption = compose_tiktok_caption({
            "title": "A fábrica caiu",
            "description": "O time perdeu tudo no servidor.",
            "hashtags": ["#minecraft", "#gameplay"],
            "legenda_tiktok": "A fábrica caiu\n\nO time perdeu tudo.",
        })
        self.assertIn("#minecraft", caption)
        self.assertIn("#gameplay", caption)

    def test_tiktok_status_wait_stops_on_inbox_or_failure(self):
        with patch.object(tiktok, "fetch_status", side_effect=[
            {"status": "PROCESSING_UPLOAD"}, {"status": "SEND_TO_USER_INBOX"}
        ]), patch.object(tiktok.time, "sleep"):
            result = tiktok.wait_for_status("pub", token="token", timeout=10, interval=2)
        self.assertEqual(result["status"], "SEND_TO_USER_INBOX")

    def test_tiktok_direct_post_sends_public_metadata_fields(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4") as video, patch.object(
            tiktok, "can_direct", return_value=True
        ), patch.object(tiktok, "_send", return_value={"publish_id": "p", "status": "PUBLISH_COMPLETE"}) as send:
            tiktok.upload_direct(video.name, "Legenda #minecraft")
        post_info = send.call_args.args[2]
        self.assertEqual(post_info["title"], "Legenda #minecraft")
        self.assertIn("privacy_level", post_info)
        self.assertIn("brand_content_toggle", post_info)
        self.assertIn("is_aigc", post_info)

    def test_verify_parse_reprova_com_falha_e_ignora_aviso(self):
        stdout = (
            "[OK   ] resolucao                   1080x1920 (esperado 1080x1920)\n"
            "[FALHA] duracao                     10.00s (faixa 15-65s)\n"
            "[AVISO] fps                         29.97 (esperado 30.00)\n"
            "Resultado: REPROVADO | 1 falha(s), 1 aviso(s)\n"
        )
        verif = _parse_verify(stdout, 1)
        self.assertFalse(verif["passed"])
        self.assertEqual(len(verif["falhas"]), 1)
        self.assertIn("duracao", verif["falhas"][0])
        self.assertEqual(len(verif["avisos"]), 1)
        ok = _parse_verify("Resultado: APROVADO | 0 falha(s), 2 aviso(s)\n", 0)
        self.assertTrue(ok["passed"])
        self.assertFalse(ok["falhas"])


    def test_face_head_transform_and_deadband_freeze(self):
        d = {"t": 1.0, "fx": 0.5, "fy": 0.70, "fw": 0.10, "fh": 0.20}
        hd = face._head_det(d)
        self.assertAlmostEqual(hd["fh"], 0.20 * face.HEAD_SCALE)
        self.assertAlmostEqual(hd["fy"], 0.70 - face.HEAD_UP * 0.20)
        tremendo = [[i * 0.5, 0.5 + (0.001 if i % 2 else -0.001),
                     0.6 + (0.001 if i % 3 else -0.001), 0.2] for i in range(10)]
        frozen = face._freeze_axes(tremendo)
        self.assertEqual(len({p[1] for p in frozen}), 1)
        self.assertEqual(len({p[2] for p in frozen}), 1)
        andando = [[i * 0.5, 0.1 + i * 0.05, 0.6, 0.2] for i in range(10)]
        movido = face._freeze_axes(andando)
        self.assertGreater(max(p[1] for p in movido) - min(p[1] for p in movido), face.DEADBAND)

    def test_face_center_after_clamp_keeps_head_inside_zoom_window(self):
        track = [[0.0, 0.134, 0.640, 0.211], [21.0, 0.134, 0.640, 0.211], [42.0, 0.134, 0.640, 0.211]]
        fcx, fcy = render._face_center(track, 1920, 1080, 504, 895)
        cy = min(max(0.640 * 1080 - 895 * 0.40, 0.0), 1080 - 895)
        self.assertAlmostEqual(cy, 185.0)
        self.assertAlmostEqual(fcy, (0.640 * 1080 - cy) / 895, places=3)
        self.assertNotAlmostEqual(fcy, 0.40, places=1)
        kmax = 2.2
        win_y = cy + (fcy - 0.40 / kmax) * 895
        win_h = 895 / kmax
        cabeca_topo = (0.640 - 0.5 * 0.211) * 1080
        cabeca_base = (0.640 + 0.5 * 0.211) * 1080
        self.assertGreaterEqual(cabeca_topo - win_y, 10)
        self.assertGreaterEqual((win_y + win_h) - cabeca_base, 10)


if __name__ == "__main__":
    unittest.main()
