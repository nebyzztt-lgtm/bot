import subprocess
import sys
import time
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_SCRIPT = os.path.join(SCRIPT_DIR, "bot.py")

def run_bot_forever():
    print("====================================================")
    print("  SUPERVISOR DEL BOT TELEGRAM - MODO 24/7 SIEMPRE ON")
    print("  Si el bot se detiene por error o caída de red,")
    print("  este supervisor lo reiniciará automáticamente.")
    print("====================================================")
    
    while True:
        try:
            print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Iniciando bot.py...")
            process = subprocess.run([sys.executable, BOT_SCRIPT], cwd=SCRIPT_DIR)
            code = process.returncode
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Proceso finalizado con código {code}.")
            if code == 0:
                print("El bot se cerró normalmente. Reiniciando en 3 segundos...")
            else:
                print("Reanudando bot en 3 segundos para mantenerlo siempre activo...")
            time.sleep(3)
        except KeyboardInterrupt:
            print("\nSupervisor detenido manualmente.")
            break
        except Exception as e:
            print(f"Error en supervisor: {e}. Reintentando en 5 segundos...")
            time.sleep(5)

if __name__ == "__main__":
    run_bot_forever()
