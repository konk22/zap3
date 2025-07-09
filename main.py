import re

import camera
import api_client
import display
import config
import os
import pygame
import asyncio
import logging
from pydantic import BaseModel

class ConfigModel(BaseModel):
    LOG_LEVEL: str = "INFO"

configLog = ConfigModel()

log_level = getattr(logging, configLog.LOG_LEVEL.upper(), logging.INFO)

logging.basicConfig(
    filename='app.log',
    level=log_level,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

async def capture_with_spinner(cap, screen, font, spinner_angle):
    """Асинхронный захват кадра с одновременной анимацией спиннера."""
    frame = None
    while frame is None:
        # Запускаем захват кадра и анимацию спиннера параллельно
        capture_task = asyncio.create_task(camera.capture_with_delay(cap))
        while not capture_task.done():
            spinner_angle, running = await display.show_waiting_screen(screen, font, spinner_angle)
            if not running:
                capture_task.cancel()
                return None, spinner_angle, False
            await asyncio.sleep(0)  # Уступаем управление

        frame = await capture_task
        if frame is None:  # Если выход по ESC
            return None, spinner_angle, False

    return frame, spinner_angle, True


async def api_with_spinner(photo_path, api_key, api_scope, screen, font, spinner_angle):
    """Асинхронный API-запрос с одновременной анимацией спиннера."""
    api_task = asyncio.create_task(api_client.get_dossier(photo_path, api_key, api_scope))
    while not api_task.done():
        spinner_angle, running = await display.show_api_loading_screen(screen, font, spinner_angle)
        if not running:
            api_task.cancel()
            return None, None, spinner_angle, False
        await asyncio.sleep(0)  # Уступаем управление

    try:
        dossier, request_number = await api_task
        return dossier, request_number, spinner_angle, True
    except Exception as e:
        logging.error(f"Ошибка API в задаче: {str(e)}")
        return None, None, spinner_angle, True


async def main():
    # Инициализация Pygame и режима окна
    pygame.init()
    screen = pygame.display.set_mode(
        (config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT),
        pygame.FULLSCREEN if config.FULLSCREEN_MODE else 0
    )
    pygame.mouse.set_visible(False)  # Отключение курсора мыши
    font = pygame.font.SysFont("arial", 36)

    # # Инициализация камеры
    # try:
    #     cap = camera.init_camera(config.CAMERA_SOURCE, config.CAMERA_AUTH)
    # except Exception as e:
    #     logging.error(f"Ошибка инициализации камеры: {str(e)}")
    #     await display.show_error(screen, font, f"Ошибка камеры: {str(e)}")
    #     pygame.quit()
    #     return

    # Анимация спиннера
    spinner_angle = 0

    while True:
        # Инициализация камеры
        try:
            cap = camera.init_camera(config.CAMERA_SOURCE, config.CAMERA_AUTH)
        except Exception as e:
            logging.error(f"Ошибка инициализации камеры: {str(e)}")
            await display.show_error(screen, font, f"Ошибка камеры: {str(e)}")
            pygame.quit()
            return
        # Захват кадра с одновременной анимацией спиннера
        frame, spinner_angle, running = await capture_with_spinner(cap, screen, font, spinner_angle)
        if not running:
            camera.release_camera(cap)
            pygame.quit()
            logging.info("Программа завершена")
            return

        if frame is not None:
            # Сохранение фото
            try:
                photo_path = camera.save_photo(frame, config.PHOTO_PATH)
                logging.info(f"Фото сохранено: {photo_path}")
            except Exception as e:
                logging.error(f"Ошибка сохранения фото: {str(e)}")
                await display.show_error(screen, font, f"Ошибка сохранения фото: {str(e)}")
                continue
            camera.release_camera(cap)

            # Выполнение API-запроса с одновременной анимацией спиннера
            dossier = None
            request_number = None
            try:
                dossier, request_number, spinner_angle, running = await api_with_spinner(
                    photo_path, config.API_KEY, config.API_SCOPE, screen, font, spinner_angle
                )
                if not running:
                    camera.release_camera(cap)
                    pygame.quit()
                    logging.info("Программа завершена во время загрузки")
                    return
            except Exception as e:
                logging.error(f"Ошибка API: {str(e)}")
                await display.show_error(screen, font, f"Ошибка API: {str(e)}")
                if os.path.exists(photo_path):
                    os.remove(photo_path)
                continue

            # Если досье получено, отображаем результат
            if dossier is not None:
                try:
                    dossier = re.sub(r'\n\s*\n+', '\n', dossier.strip())
                    if not display.show_result(screen, photo_path, dossier, request_number):
                        logging.info("Отображение результата прервано пользователем")
                        if os.path.exists(photo_path):
                            os.remove(photo_path)
                        continue
                except Exception as e:
                    logging.error(f"Ошибка отображения результата: {str(e)}")
                    await display.show_error(screen, font, f"Ошибка отображения: {str(e)}")
            else:
                await display.show_error(screen, font, "Ошибка соединения с API. Попробуйте снова.")
                if os.path.exists(photo_path):
                    os.remove(photo_path)
                continue

            # Удаление временного фото
            if os.path.exists(photo_path):
                os.remove(photo_path)
                logging.info(f"Фото удалено: {photo_path}")

    # Освобождение ресурсов
    camera.release_camera(cap)
    pygame.quit()
    logging.info("Программа завершена")


if __name__ == "__main__":
    asyncio.run(main())
