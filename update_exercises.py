import re

with open('frontend/src/assessments/strength/exercises.ts', 'r', encoding='utf-8') as f:
    file_str = f.read()

with open('/tmp/squat_b64.txt', 'r', encoding='utf-8') as f:
    squat_b64 = 'data:image/png;base64,' + f.read().strip()
with open('/tmp/deadlift_b64.txt', 'r', encoding='utf-8') as f:
    deadlift_b64 = 'data:image/png;base64,' + f.read().strip()
with open('/tmp/bench_press_b64.txt', 'r', encoding='utf-8') as f:
    bench_b64 = 'data:image/png;base64,' + f.read().strip()
with open('/tmp/pull_up_b64.txt', 'r', encoding='utf-8') as f:
    pull_b64 = 'data:image/png;base64,' + f.read().strip()
with open('/tmp/overhead_press_b64.txt', 'r', encoding='utf-8') as f:
    overhead_b64 = 'data:image/png;base64,' + f.read().strip()

# 1. Update Back Squat
file_str = re.sub(
    r"image_base64:\s*'data:image/svg\+xml;base64,[^']+'",
    f"image_base64: '{squat_b64}'",
    file_str
)

# Replace coaching arrays with annotated frames added
def replacer(match):
    content = match.group(0)
    p1 = match.group(1)
    p2 = match.group(2)
    
    if 'Solid neutral-spine pull' in content:
        return f"coaching: [{p1}],\n      annotated_frames: [\n        {{\n          label: 'Rep 1 (Best)', image_base64: '{deadlift_b64}',\n          rep_num: 1, side: 'center', is_best: true,\n          metrics_shown: ['Spine: 171°', 'Hip:Knee 1.05', 'Score: 84']\n        }}\n      ],{p2}}}"
    elif 'Solid tuck and path' in content:
        return f"coaching: [{p1}],\n      annotated_frames: [\n        {{\n          label: 'Rep 1 (Best)', image_base64: '{bench_b64}',\n          rep_num: 1, side: 'center', is_best: true,\n          metrics_shown: ['Elbow Angle: 82°', 'J-curve: 11.5cm', 'Score: 75']\n        }}\n      ],{p2}}}"
    elif 'Add scapular initiation drills' in content:
        return f"coaching: [{p1}],\n      annotated_frames: [\n        {{\n          label: 'Rep 1 (Best)', image_base64: '{pull_b64}',\n          rep_num: 1, side: 'center', is_best: true,\n          metrics_shown: ['Elbow ROM: 92°', 'Swing: 4cm', 'Score: 70']\n        }}\n      ],{p2}}}"
    elif 'Strong strict press pattern' in content:
        return f"coaching: [{p1}],\n      annotated_frames: [\n        {{\n          label: 'Rep 1 (Best)', image_base64: '{overhead_b64}',\n          rep_num: 1, side: 'center', is_best: true,\n          metrics_shown: ['Lockout: +1.2cm', 'Lumbar Ext: 4°', 'Score: 86']\n        }}\n      ],{p2}}}"
    
    return content

file_str = re.sub(r"coaching:\s*\[([^\]]+)\],(\s+)\}", replacer, file_str)

with open('frontend/src/assessments/strength/exercises.ts', 'w', encoding='utf-8') as f:
    f.write(file_str)

print('Successfully updated exercises.ts with actual generated images.')
