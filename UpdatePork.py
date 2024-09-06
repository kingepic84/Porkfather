import psutil,subprocess,sys
from subprocess import DEVNULL
for process in psutil.process_iter():
    if "Porkbot.py" in process.name():
        print(process.name)
        process.terminate()
        process.wait()
git = subprocess.run(["git", "pull"], stdout=sys.stdout, stderr=sys.stderr)
pork = subprocess.Popen(["nohup python3 Porkbot.py"], stdout=sys.stdout, stderr=sys.stderr, shell=True)
print("Porkfather Restarted")

