"""query_sku.py —— tra tất cả offer của mã sản phẩm (SKU) được chỉ định

Cách dùng:
  python query_sku.py g1.2tb.ai.subs_variant [SKU khác...]
  python query_sku.py --20tb | --30tb | --ultra
"""
import json
import re
import sys
import threading
import time

import frida

import ultra0


def _expand_skus(args: list[str]) -> list[str]:
    if not args:
        return ["g1.2tb.ai.subs_variant"]
    out: list[str] = []
    for a in args:
        if a == "--20tb":
            out.extend(ultra0.U20_SKUS)
        elif a == "--30tb":
            out.extend(ultra0.U30_SKUS)
        elif a == "--ultra":
            out.extend(ultra0.U20_SKUS + ultra0.U30_SKUS)
        else:
            out.append(a)
    return list(dict.fromkeys(out))


def _fmt_micros(micros: str) -> str:
    if micros == "0":
        return "Miễn phí"
    try:
        return f"${int(micros) / 1_000_000:.2f}"
    except Exception:
        return micros


def main():
    skus = _expand_skus(sys.argv[1:])
    ultra0.ADB = ultra0.find_adb()
    ultra0.pick_device()
    ultra0.ensure_root()
    ultra0.ensure_frida_server()
    ultra0.ensure_module_apk()
    ultra0.ensure_vending()

    dev = frida.get_usb_device(timeout=10)
    pid = 0
    for p in dev.enumerate_processes():
        if "subscriptions.red" in p.name or p.name == "Google One":
            pid = p.pid
            break
    if not pid:
        pid = ultra0.launch_app()
    if not pid:
        raise SystemExit("Không tìm thấy tiến trình Google One")

    js = ultra0.build_js("auto", True, allow_discount=True)
    js = re.sub(r'var PRODUCTS=\[[^\]]*\];', 'var PRODUCTS=' + json.dumps(skus) + ';', js, count=1)

    sess = dev.attach(pid)
    done = threading.Event()
    offers = []

    def on_msg(m, d):
        p = m.get("payload") or {}
        if p.get("ev") == "offer":
            offers.append(p)
        elif p.get("ev") in ("list_only", "no_trial", "query_err", "no_offers", "pd"):
            if p.get("ev") != "pd":
                done.set()

    sc = sess.create_script(js)
    sc.on("message", on_msg)
    sc.load()
    done.wait(timeout=25)
    time.sleep(1)

    print(f"\n=== {', '.join(skus)} ===")
    if not offers:
        print("  (Không có offer nào được trả về)")
    for o in offers:
        micros = str(o.get("micros", ""))
        base_micros = str(o.get("base_micros", micros))
        price = _fmt_micros(micros)
        base_info = f" (gốc {_fmt_micros(base_micros)})" if base_micros and base_micros != micros else ""
        oid = str(o.get("id"))
        print(f"  [{o.get('product')}] offerId={oid:22s} {price:>9s}{base_info}  {o.get('period')}   [{o.get('title') or o.get('name') or ''}]")
        if micros == "0" or (oid and oid != "null") or (base_micros and base_micros != micros):
            print(f"      token={o.get('token')}")
    try:
        sess.detach()
    except Exception:
        pass


if __name__ == "__main__":
    main()
