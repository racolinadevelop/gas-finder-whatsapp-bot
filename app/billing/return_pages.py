"""Static mobile return screen for Stripe TEST. Never claim payment from redirect."""

from html import escape

from fastapi.responses import HTMLResponse


def stripe_test_return_page(kind: str) -> HTMLResponse:
    views = {
        "success": (
            "Vuelve a WhatsApp",
            "Has terminado el formulario de Stripe TEST.",
            "El bot confirmará tu Premium cuando reciba y verifique el pago de prueba. "
            "Si la confirmación tarda, abre «Mi plan» en el chat.",
            "Return to WhatsApp",
            "Only a verified Stripe webhook activates Premium, not this page.",
        ),
        "cancel": (
            "Inscripción sin completar",
            "Puedes volver al chat cuando quieras.",
            "No se ha activado ninguna suscripción nueva por abrir esta página. "
            "Si quieres intentarlo otra vez, abre «Mi plan» en WhatsApp.",
            "Checkout not completed",
            "Return to your WhatsApp chat to try again.",
        ),
        "account": (
            "Vuelve a WhatsApp",
            "Has salido de la gestión de tu suscripción de prueba.",
            "Regresa a «Mi plan» en el chat para consultar tu estado actualizado.",
            "Return to WhatsApp",
            "Open My plan in WhatsApp to check your subscription status.",
        ),
    }
    title, heading, explanation, english_title, english_info = views[kind]
    # All content is static; never embed a phone number, checkout session ID
    # or Stripe API response into a public redirect destination.
    html = """<!doctype html>
<html lang="es"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light">
<title>Gas Finder · {title}</title>
<style>
:root {{ font-family: system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
color: #10241f; background: #f4faf6; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; min-height:100vh; display:grid; place-items:center; padding:20px; }}
main {{ width:100%; max-width:480px; padding:32px 26px; background:white;
border-radius:24px; box-shadow:0 12px 50px rgba(16,45,28,.12); }}
.badge {{ display:inline-block; padding:8px 12px; border-radius:24px;
color:#17623c; background:#dff6e7; font-size:13px; font-weight:750; }}
h1 {{ margin:23px 0 10px; font-size:29px; line-height:1.18; }}
p {{ line-height:1.55; font-size:16px; }}
.note {{ color:#4a6056; }}
a.button {{ display:block; margin:26px 0 15px; padding:15px 18px;
border-radius:13px; background:#128c55; color:#fff; font-weight:700;
text-decoration:none; text-align:center; }}
small {{ color:#597268; font-size:13px; line-height:1.5; display:block; }}
hr {{ margin:23px 0; border:0; border-top:1px solid #e1eee6; }}
</style>
</head><body><main>
<span class="badge">⛽ Gas Finder · Stripe TEST</span>
<h1>{title}</h1>
<p>{heading}</p>
<p class="note">{explanation}</p>
<a class="button" href="whatsapp://">Abrir WhatsApp · Open WhatsApp</a>
<small>Si el botón no te lleva al chat, toca «WhatsApp» o Atrás en la parte
superior del navegador y abre «Mi plan». El navegador integrado no siempre
permite cerrarse automáticamente.</small>
<hr><small><strong>{english_title}</strong><br>{english_info}</small>
<small style="margin-top:12px">Solo pruebas: no se realizan cobros reales.<br>
TEST mode only: no real charges.</small>
</main></body></html>""".format(
        title=escape(title), heading=escape(heading),
        explanation=escape(explanation),
        english_title=escape(english_title), english_info=escape(english_info),
    )
    return HTMLResponse(
        html, headers={
            "Cache-Control": "no-store, private",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Content-Security-Policy": (
                "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
                "style-src 'unsafe-inline'; form-action 'none'"
            ),
        },
    )
