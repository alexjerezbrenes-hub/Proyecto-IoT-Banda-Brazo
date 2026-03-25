import cv2
import numpy as np
import time
import requests
from collections import deque

SERIAL_ENABLE = True
SER_PORT = "COM5"
SER_BAUD = 115200
BACKEND_URL = "http://localhost:8080/datos"

AUTO_SEND_N = True
OPEN_MS = 350

AREA_MIN = 1500
HIST_LEN = 10

OBJETO_POR_COLOR = {
    "ROJO": "tuerca",
    "VERDE": "tornillo",
    "AZUL": "arandela"
}

try:
    ser = None
    if SERIAL_ENABLE:
        import serial
        ser = serial.Serial(SER_PORT, SER_BAUD, timeout=0.1)
        time.sleep(2)
        print(f"[SERIAL] Conectado a {SER_PORT} @ {SER_BAUD}")
except Exception as e:
    print("[SERIAL] No se pudo abrir el puerto:", e)
    ser = None


def send_serial(txt: str):
    if ser is None:
        print(f"[DEMO SERIAL] -> {txt}")
        return

    try:
        ser.write(txt.encode("ascii"))
    except Exception as e:
        print("[SERIAL ERROR]", e)


def enviar_backend(color, objeto):
    data = {
        "color": color,
        "objeto": objeto,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    try:
        r = requests.post(BACKEND_URL, json=data, timeout=3)
        if r.status_code not in (200, 201):
            print("[BACKEND] Respuesta:", r.status_code, r.text)
    except Exception as e:
        print("[BACKEND ERROR]", e)


def abrir_camara(indices=(0, 1, 2, 3), backends=(cv2.CAP_DSHOW, cv2.CAP_MSMF, 0),
                 w=1280, h=720, fps=30, forzar_mjpg=True):
    for i in indices:
        for b in backends:
            cap = cv2.VideoCapture(i, b)

            if not cap.isOpened():
                cap.release()
                continue

            if forzar_mjpg:
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

            cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            cap.set(cv2.CAP_PROP_FPS, fps)

            ok, frame = cap.read()
            if ok and frame is not None:
                print(f"[OK] Cámara abierta: index={i} backend={b} | {frame.shape[1]}x{frame.shape[0]}")
                return cap, i, b

            cap.release()

    return None, None, None


def dibujar_deteccion(frame, contour, color_bgr, etiqueta):
    x, y, w, h = cv2.boundingRect(contour)
    area = cv2.contourArea(contour)
    cx, cy = x + w // 2, y + h // 2

    cv2.rectangle(frame, (x, y), (x + w, y + h), color_bgr, 2)
    cv2.circle(frame, (cx, cy), 5, color_bgr, -1)
    cv2.putText(
        frame,
        f"{etiqueta} | area={int(area)}",
        (x, max(30, y - 10)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        color_bgr,
        2,
        cv2.LINE_AA
    )


RANGOS = {
    "ROJO": [
        ((0, 120, 70), (10, 255, 255)),
        ((170, 120, 70), (179, 255, 255)),
    ],
    "VERDE": [
        ((36, 80, 70), (89, 255, 255))
    ],
    "AZUL": [
        ((90, 80, 70), (130, 255, 255))
    ],
}

COLORES_BGR = {
    "ROJO": (0, 0, 255),
    "VERDE": (0, 255, 0),
    "AZUL": (255, 0, 0),
}

CODE = {
    "ROJO": "R",
    "VERDE": "V",
    "AZUL": "A"
}

hist_labels = deque(maxlen=HIST_LEN)

cap, idx, backend = abrir_camara()

if cap is None:
    raise RuntimeError("No pude abrir la cámara.")

print(f"Usando cámara índice {idx} con backend {backend}.")
print("Pulsa 'q' para salir, 'h' para ocultar/mostrar máscaras.")

accion_actual = "NINGUNA"
mostrar_masks = True
gate_until = 0.0

while True:
    ok, frame = cap.read()
    if not ok:
        print("No pude leer frame.")
        break

    blur = cv2.GaussianBlur(frame, (5, 5), 0)
    hsv = cv2.cvtColor(blur, cv2.COLOR_BGR2HSV)

    detecciones = []

    for label, rangos in RANGOS.items():
        mask_total = None

        for (lo, hi) in rangos:
            lo = np.array(lo, dtype=np.uint8)
            hi = np.array(hi, dtype=np.uint8)

            mask = cv2.inRange(hsv, lo, hi)
            mask_total = mask if mask_total is None else cv2.bitwise_or(mask_total, mask)

        kernel = np.ones((5, 5), np.uint8)
        mask_total = cv2.morphologyEx(mask_total, cv2.MORPH_OPEN, kernel, iterations=1)
        mask_total = cv2.morphologyEx(mask_total, cv2.MORPH_CLOSE, kernel, iterations=2)

        cnts, _ = cv2.findContours(mask_total, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if cnts:
            c = max(cnts, key=cv2.contourArea)
            area = cv2.contourArea(c)

            if area >= AREA_MIN:
                detecciones.append((label, c, area))

        if mostrar_masks:
            vis_mask = cv2.cvtColor(mask_total, cv2.COLOR_GRAY2BGR)
            cv2.putText(
                vis_mask,
                label,
                (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                COLORES_BGR[label],
                2,
                cv2.LINE_AA
            )
            cv2.imshow(f"Mask {label}", vis_mask)

    if detecciones:
        label_dom, cont_dom, _ = max(detecciones, key=lambda t: t[2])
        dibujar_deteccion(frame, cont_dom, COLORES_BGR[label_dom], label_dom)
        hist_labels.append(label_dom)
    else:
        hist_labels.append("NINGUNA")

    vals, counts = np.unique(list(hist_labels), return_counts=True)
    label_stable = vals[np.argmax(counts)]

    if label_stable != accion_actual:
        accion_actual = label_stable

        if accion_actual != "NINGUNA":
            objeto = OBJETO_POR_COLOR.get(accion_actual, "objeto desconocido")
            print(f"[ACCION] Detecté color {accion_actual} -> objeto: {objeto}")

            if SERIAL_ENABLE:
                send_serial(CODE[accion_actual])

            enviar_backend(accion_actual, objeto)

            if AUTO_SEND_N:
                gate_until = time.time() + OPEN_MS / 1000.0
        else:
            print("[ACCION] Sin color dominante")

    if SERIAL_ENABLE and AUTO_SEND_N and gate_until and time.time() >= gate_until:
        send_serial("N")
        gate_until = 0.0

    cv2.putText(frame, f"Color: {label_stable}", (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)

    objeto_actual = OBJETO_POR_COLOR.get(label_stable, "ninguno") if label_stable != "NINGUNA" else "ninguno"
    cv2.putText(frame, f"Objeto: {objeto_actual}", (20, 80),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)

    cv2.putText(frame, "q = salir | h = masks ON/OFF", (20, 120),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (240, 240, 240), 2, cv2.LINE_AA)

    cv2.imshow("Deteccion de colores", frame)

    k = cv2.waitKey(1) & 0xFF
    if k == ord('q'):
        break
    if k == ord('h'):
        mostrar_masks = not mostrar_masks
        if not mostrar_masks:
            for wname in list(RANGOS.keys()):
                try:
                    cv2.destroyWindow(f"Mask {wname}")
                except:
                    pass

cap.release()
cv2.destroyAllWindows()

try:
    if ser:
        ser.close()
except:
    pass
