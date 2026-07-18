import subprocess, os, sys

html_path = os.path.abspath('test_card_layout.html')
chrome_paths = [
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
]

for cp in chrome_paths:
    if os.path.exists(cp):
        print(f'Found Chrome at {cp}')
        file_url = 'file:///' + html_path.replace('\\', '/')
        result = subprocess.run(
            [cp, '--headless', '--disable-gpu', '--screenshot=test_layout.png',
             '--window-size=1400,800', file_url],
            capture_output=True, text=True, timeout=20
        )
        if result.stderr:
            print('Stderr:', result.stderr[:500])
        if os.path.exists('test_layout.png'):
            print(f'Screenshot OK! Size: {os.path.getsize("test_layout.png")} bytes')
        else:
            print('Screenshot file not created')
        break
else:
    print('Chrome not found, trying "chrome" in PATH...')
    result = subprocess.run(['where', 'chrome'], capture_output=True, text=True, timeout=5)
    print(result.stdout[:200] if result.stdout else 'Not found')
