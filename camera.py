import cv2
import os
import time
import logging
import asyncio
from config import CAMERA_SOURCE, CAMERA_AUTH, PHOTO_RESOLUTION, PHOTO_DELAY, MIN_AREA_PERCENT, FRAME_SKIP, \
    FACE_FRAME_COLOR, FACE_FRAME_THICKNESS

# Настройка логирования
logging.basicConfig(filename='app.log', level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')
# Счетчик кадров
frame_counter = 0

def init_camera(source=CAMERA_SOURCE, auth=CAMERA_AUTH):
    """Инициализация камеры (локальной или RTSP)."""
    try:
        if isinstance(source, int):
            cap = cv2.VideoCapture(source)
            logging.info(f"Попытка инициализации локальной камеры с индексом {source}")
        else:
            if auth:
                auth_str = f"{auth.replace(':', ':')}@"
                rtsp_url = source.replace("rtsp://", f"rtsp://{auth_str}")
            else:
                rtsp_url = source
            cap = cv2.VideoCapture(rtsp_url)
            logging.info(f"Попытка инициализации RTSP-потока: {rtsp_url}")

        if not cap.isOpened():
            logging.error(f"Не удалось открыть камеру: {source}")
            raise Exception(f"Не удалось открыть камеру: {source}")

        # Сохраняем исходное разрешение камеры
        original_width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        original_height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        logging.info(f"Исходное разрешение камеры: {original_width}x{original_height}")

        ret, _ = cap.read()
        if not ret:
            cap.release()
            logging.error(f"Не удалось захватить кадр с камеры: {source}")
            raise Exception(f"Не удалось захватить кадр с камеры: {source}")

        logging.info(f"Камера инициализирована, источник: {source}")
        return cap

    except Exception as e:
        logging.error(f"Ошибка инициализации камеры: {str(e)}")
        raise

async def create_face(cap, cascade_path="haarcascade_frontalface_alt.xml"):
    """Асинхронная детекция лица в кадре и проверка площади."""
    global frame_counter
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + cascade_path)

    frame_counter += 1
    if frame_counter % FRAME_SKIP != 0:
        return None, False, None

    ret, original_frame = cap.read()
    if not ret:
        logging.warning("Не удалось захватить кадр")
        return None, False, None

    # Уменьшаем кадр до 640x480 для анализа
    analysis_frame = cv2.resize(original_frame, (640, 480))
    gray = cv2.cvtColor(analysis_frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))

    if len(faces) == 0:
        return original_frame, False, None

    # Масштабируем координаты лица обратно к исходному разрешению
    scale_x = original_frame.shape[1] / 640
    scale_y = original_frame.shape[0] / 480

    frame_area = 640 * 480  # Площадь для анализа
    max_area = 0
    max_face = None
    for (x, y, w, h) in faces:
        area = w * h
        if area > max_area:
            max_area = area
            max_face = (int(x * scale_x), int(y * scale_y), int(w * scale_x), int(h * scale_y))

    if max_area / frame_area < MIN_AREA_PERCENT:
        logging.info(f"Лицо занимает менее {MIN_AREA_PERCENT * 100}% кадра")
        return original_frame, False, None

    if max_face is not None:
        x, y, w, h = max_face
        cv2.rectangle(original_frame, (x, y), (x + w, y + h), FACE_FRAME_COLOR, FACE_FRAME_THICKNESS)
        logging.info(f"Рамка добавлена: цвет {FACE_FRAME_COLOR}, толщина {FACE_FRAME_THICKNESS}")

    logging.info(f"Обнаружено лицо, площадь: {max_area / frame_area * 100:.2f}%")
    return original_frame, True, max_face

def save_photo(frame, path):
    """Сохранение фото в формате PNG с проверкой качества."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    success = cv2.imwrite(path, frame, [int(cv2.IMWRITE_PNG_COMPRESSION), 0])
    if not success or not os.path.exists(path):
        logging.error(f"Не удалось сохранить изображение: {path}")
        raise Exception(f"Не удалось сохранить изображение: {path}")
    logging.info(f"Изображение сохранено: {path}, размер: {os.path.getsize(path)} байт")
    return path

async def check_exit():
    """Асинхронная проверка нажатия клавиши ESC для выхода."""
    if cv2.waitKey(1) & 0xFF == 27:
        logging.info("Выход по клавише ESC")
        return False
    return True

def release_camera(cap):
    """Освобождение камеры."""
    cap.release()
    cv2.destroyAllWindows()
    logging.info("Камера освобождена")

async def capture_with_delay(cap):
    """Асинхронный захват фото с задержкой и проверкой площади."""
    start_time = None
    face_detected = False

    while True:
        frame, detected, face = await create_face(cap)
        if frame is None and not detected:
            if not await check_exit():
                return None
            await asyncio.sleep(0.01)
            continue

        if not detected:
            start_time = None
            face_detected = False
        else:
            if not face_detected:
                start_time = time.time()
                face_detected = True
                logging.info("Начало отсчета задержки для снимка")
            elif time.time() - start_time >= PHOTO_DELAY:
                logging.info("Снимок сделан")
                return frame

        if frame is not None:
            # cv2.imshow('Camera Feed', frame)
            pass

        if not await check_exit():
            return None

        await asyncio.sleep(0.01)

    return None
