"""Contact sheet of every answered frame with printed time, pose and the Cosmos verdict (base marks only if base_visible; none were)."""
import json, sys
from pathlib import Path
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parent))
import vcommon as v
obs = json.loads((v.HERE / 'observations.json').read_text())['observations']
cols, w, h = 3, 480, 270
sheet = Image.new('RGB', (cols * w, ((len(obs) + cols - 1) // cols) * (h + 16)), 'white'); d = ImageDraw.Draw(sheet)
for i, o in enumerate(obs):
    x, y = (i % cols) * w, (i // cols) * (h + 16)
    sheet.paste(Image.open(v.TOOLS / o['imagePath']).convert('RGB').resize((w, h)), (x, y))
    if o['base_visible']:
        px, py = x + o['x_base'] * w, y + o['y_base'] * h; d.ellipse((px - 6, py - 6, px + 6, py + 6), outline='red', width=2)
    d.text((x + 3, y + h + 2), f"{o['poseId']} {o['printedTime'][11:19]} base_visible={o['base_visible']} conf={o['confidence']} [{o['printedTimeStatus']}]", fill='black')
sheet.save(v.HERE / 'contact/answered-frames.jpg', quality=88)
