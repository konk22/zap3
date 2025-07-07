import pygame
import pygame.gfxdraw
import os
from gtts import gTTS
from config import DISPLAY_WIDTH, DISPLAY_HEIGHT, AUDIO_PATH, FULLSCREEN_MODE, ALLOWED_TTS, DOSSIER_DISPLAY_DURATION, \
    DOSSIERS_TEXT, DOSSIERS_TEXT_LOCATION, QR_TEXT, TEXT_SPEED
import logging
import asyncio
import math
from datetime import datetime
from camera import init_camera

# Настройка логирования
logging.basicConfig(filename='app.log', level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')


def wrap_text(text, font, max_width):
    """Перенос текста для ограничения ширины с поддержкой переносов строк."""
    lines = []
    for paragraph in text.split('\n'):
        if not paragraph:
            lines.append("")
            continue
        words = paragraph.split(" ")
        current_line = ""
        for word in words:
            test_line = f"{current_line}{word} "
            test_surface = font.render(test_line.strip(), True, (255, 255, 255))
            if test_surface.get_width() <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line.strip())
                current_line = f"{word} "
        if current_line:
            lines.append(current_line.strip())

    surfaces = []
    for line in lines:
        if line:
            surfaces.append(font.render(line, True, (255, 255, 255)))
        else:
            surfaces.append(None)

    return surfaces


def draw_spinner(screen, center, radius, angle):
    """Отрисовка спиннера."""
    points = []
    for i in range(8):
        rad = math.radians(angle + i * 45)
        alpha = 255 * (1 - i / 8)
        x = center[0] + radius * math.cos(rad)
        y = center[1] + radius * math.sin(rad)
        points.append((x, y, alpha))

    for x, y, alpha in points:
        pygame.draw.circle(screen, (255, 255, 255, int(alpha)), (int(x), int(y)), 5)


def draw_progress_ring(screen, center, radius, thickness, progress):
    """Отрисовка сглаженного кольцевого прогресс-бара."""
    for i in range(thickness):
        pygame.gfxdraw.arc(
            screen,
            int(center[0]), int(center[1]),
            radius - i,
            0,
            360,
            (100, 100, 100)
        )
    start_angle = -90
    end_angle = start_angle + 360 * progress
    for i in range(thickness):
        pygame.gfxdraw.arc(
            screen,
            int(center[0]), int(center[1]),
            radius - i,
            int(start_angle),
            int(end_angle),
            (255, 255, 255)
        )


async def check_events():
    """Асинхронная проверка событий выхода (Ctrl+Q или ESC)."""
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            logging.info("Выход по закрытию окна")
            return False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_q and event.mod & pygame.KMOD_CTRL:
                logging.info("Выход по Ctrl + Q")
                return False
            if event.key == pygame.K_ESCAPE:
                logging.info("Выход по ESC")
                return False
    return True


async def show_waiting_screen(screen, font, angle):
    """Экран ожидания с асинхронным вращающимся спиннером."""
    current_angle = angle
    screen.fill((0, 0, 0))
    text = font.render("Ожидаем человека в кадре", True, (255, 255, 255))
    text_rect = text.get_rect(center=(DISPLAY_WIDTH // 2, DISPLAY_HEIGHT // 2 - 50))
    screen.blit(text, text_rect)
    draw_spinner(screen, (DISPLAY_WIDTH // 2, DISPLAY_HEIGHT // 2 + 50), 30, current_angle)
    pygame.display.flip()

    current_angle = (current_angle + 2) % 360
    if not await check_events():
        return current_angle, False
    await asyncio.sleep(0.01)

    # logging.debug(f"Отображен экран ожидания с углом {current_angle}")
    return current_angle, True


async def show_api_loading_screen(screen, font, angle):
    """Экран загрузки API с асинхронным вращающимся спиннером."""
    current_angle = angle
    screen.fill((0, 0, 0))
    text = font.render("Генерируем досье...", True, (255, 255, 255))
    text_rect = text.get_rect(center=(DISPLAY_WIDTH // 2, DISPLAY_HEIGHT // 2 - 50))
    screen.blit(text, text_rect)
    draw_spinner(screen, (DISPLAY_WIDTH // 2, DISPLAY_HEIGHT // 2 + 50), 30, current_angle)
    pygame.display.flip()

    current_angle = (current_angle + 2) % 360
    if not await check_events():
        return current_angle, False
    await asyncio.sleep(0.01)

    # logging.debug(f"Отображен экран загрузки API с углом {current_angle}")
    return current_angle, True


async def show_error(screen, font, message, duration=5):
    """Отображение сообщения об ошибке на экране."""
    screen.fill((0, 0, 0))
    lines = wrap_text(message, font, DISPLAY_WIDTH - 40)
    for i, surface in enumerate(lines):
        if surface:
            text_rect = surface.get_rect(center=(DISPLAY_WIDTH // 2, DISPLAY_HEIGHT // 2 - 50 + i * 40))
            screen.blit(surface, text_rect)
    pygame.display.flip()

    start_time = pygame.time.get_ticks() / 1000
    while (pygame.time.get_ticks() / 1000) - start_time < duration:
        if not await check_events():
            return False
        await asyncio.sleep(0.01)

    logging.info(f"Отображено сообщение об ошибке: {message}")
    return True


def show_result(screen, photo_path, dossier, request_number):
    """Отображение фото и досье на экране с опциональным озвучиванием."""
    font = pygame.font.SysFont("arial", 36)
    bold_font = pygame.font.SysFont("arial", 36, bold=True)
    timer_font = pygame.font.SysFont("arial", 24)
    qr_prompt_font = pygame.font.SysFont("arial", 30)

    qr_prompt_text = QR_TEXT
    qr_prompt_lines = wrap_text(qr_prompt_text, qr_prompt_font, DISPLAY_WIDTH // 2 - 140)  # Уменьшенная ширина для размещения справа от таймера

    try:
        image = pygame.image.load(photo_path)
        image = pygame.transform.scale(image, (DISPLAY_WIDTH // 2, DISPLAY_HEIGHT))
        logging.info(f"Фото загружено: {photo_path}")
    except Exception as e:
        logging.error(f"Ошибка загрузки фото: {str(e)}")
        return False

    header_text = f"{DOSSIERS_TEXT} {request_number}\\{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{DOSSIERS_TEXT_LOCATION}\n"
    header_surfaces = wrap_text(header_text, bold_font, DISPLAY_WIDTH // 2 - 40)

    max_text_width = DISPLAY_WIDTH // 2 - 40
    text_surfaces = wrap_text(dossier, font, max_text_width)

    if ALLOWED_TTS:
        try:
            tts = gTTS(text=dossier, lang="ru", tld="ru")
            os.makedirs(os.path.dirname(AUDIO_PATH), exist_ok=True)
            tts.save(AUDIO_PATH)
            logging.info(f"Аудиофайл создан: {AUDIO_PATH}")

            pygame.mixer.init()
            pygame.mixer.music.load(AUDIO_PATH)
            pygame.mixer.music.play()
            logging.info("Аудио воспроизводится")
        except Exception as e:
            logging.error(f"Ошибка создания или воспроизведения аудио: {str(e)}")
            return False

    header_height = sum(surface.get_height() if surface else 40 for surface in header_surfaces)

    running = True
    line_index = 0
    alpha = 0
    header_alpha = 255
    while running and line_index <= len(text_surfaces):
        screen.fill((0, 0, 0))
        screen.blit(image, (DISPLAY_WIDTH // 2, 0))

        y_offset = 20
        for surface in header_surfaces:
            if surface:
                surface.set_alpha(header_alpha)
                screen.blit(surface, (20, y_offset))
                y_offset += surface.get_height()
            else:
                y_offset += 40

        for i in range(line_index):
            if i < len(text_surfaces):
                surface = text_surfaces[i]
                surface.set_alpha(255)
                screen.blit(surface, (20, y_offset + 60 + i * 40))
            else:
                y_offset += 40  # Увеличиваем отступ для пустых строк
      
        if line_index < len(text_surfaces):
            text_surfaces[line_index].set_alpha(alpha)
            screen.blit(text_surfaces[line_index], (20, y_offset + 60 + line_index * 40))

        alpha += 10
        if alpha >= 255:
            alpha = 0
            line_index += 1
            pygame.time.wait(TEXT_SPEED)

        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q and event.mod & pygame.KMOD_CTRL:
                    logging.info("Выход по Ctrl+D")
                    running = False
                if event.key == pygame.K_ESCAPE:
                    logging.info("Выход по ESC")
                    running = False

        pygame.time.wait(20)

    if not running:
        if ALLOWED_TTS:
            pygame.mixer.music.stop()
            pygame.mixer.quit()
        return False

    if ALLOWED_TTS:
        while pygame.mixer.music.get_busy():
            screen.fill((0, 0, 0))
            screen.blit(image, (DISPLAY_WIDTH // 2, 0))
            y_offset = 20
            for surface in header_surfaces:
                if surface:
                    surface.set_alpha(255)
                    screen.blit(surface, (20, y_offset))
                    y_offset += surface.get_height()
                else:
                    y_offset += 40
            for i, surface in enumerate(text_surfaces):
                if surface:
                    surface.set_alpha(255)
                    screen.blit(surface, (20, y_offset + 60 + i * 40))
                else:
                    y_offset += 40  # Увеличиваем отступ для пустых строк
            pygame.display.flip()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_q and event.mod & pygame.KMOD_CTRL:
                        logging.info("Выход по Ctrl+D")
                        running = False
                    if event.key == pygame.K_ESCAPE:
                        logging.info("Выход по ESC")
                        running = False
            if not running:
                break
            pygame.time.wait(20)

        if not running:
            pygame.mixer.music.stop()
            pygame.mixer.quit()
            return False

    total_duration = DOSSIER_DISPLAY_DURATION
    start_time = pygame.time.get_ticks() / 1000
    last_second = -1
    timer_surface = None
    while (pygame.time.get_ticks() / 1000) - start_time < total_duration:
        screen.fill((0, 0, 0))
        screen.blit(image, (DISPLAY_WIDTH // 2, 0))

        y_offset = 20
        for surface in header_surfaces:
            if surface:
                surface.set_alpha(255)
                screen.blit(surface, (20, y_offset))
                y_offset += surface.get_height()
            else:
                y_offset += 40

        for i, surface in enumerate(text_surfaces):
            if surface:
                surface.set_alpha(255)
                screen.blit(surface, (20, y_offset + 60 + i * 40))
            else:
                y_offset += 40  # Увеличиваем отступ для пустых строк

        elapsed = (pygame.time.get_ticks() / 1000) - start_time
        remaining_time = max(0, total_duration - elapsed)
        progress = remaining_time / total_duration

        ring_center = (60, DISPLAY_HEIGHT - 60)
        draw_progress_ring(screen, ring_center, 40, 6, progress)

        seconds = int(remaining_time)
        if seconds != last_second:
            timer_text = f"{seconds:02d}"
            timer_surface = timer_font.render(timer_text, True, (255, 255, 255))
            last_second = seconds
        if timer_surface:
            timer_rect = timer_surface.get_rect(center=ring_center)
            screen.blit(timer_surface, timer_rect)

        # Отображение текста о QR-коде справа от таймера
        qr_x_offset = 120  # 60 (центр кольца) + 40 (радиус) + 20 (отступ)
        qr_y_center = DISPLAY_HEIGHT - 60  # Вертикальный центр кольца
        total_qr_height = len(qr_prompt_lines) * 30  # 30 пикселей на строку
        qr_y_offset = qr_y_center - total_qr_height // 2  # Центрирование по вертикали
        for i, surface in enumerate(qr_prompt_lines):
            if surface:
                qr_rect = surface.get_rect(left=qr_x_offset, top=qr_y_offset + i * 30)
                screen.blit(surface, qr_rect)

        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q and event.mod & pygame.KMOD_CTRL:
                    logging.info("Выход по Ctrl+D")
                    running = False
                if event.key == pygame.K_ESCAPE:
                    logging.info("Выход по ESC")
                    running = False
        if not running:
            break
        pygame.time.wait(20)

    if ALLOWED_TTS:
        pygame.mixer.music.stop()
        pygame.mixer.quit()
        if os.path.exists(AUDIO_PATH):
            os.remove(AUDIO_PATH)
            logging.info(f"Аудиофайл удален: {AUDIO_PATH}")
    logging.info("Отображение результата завершено")
    return running
