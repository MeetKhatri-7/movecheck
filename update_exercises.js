const fs = require('fs');

let fileStr = fs.readFileSync('frontend/src/assessments/strength/exercises.ts', 'utf-8');

const squat_b64 = 'data:image/png;base64,' + fs.readFileSync('/tmp/squat_b64.txt', 'utf-8').trim();
const deadlift_b64 = 'data:image/png;base64,' + fs.readFileSync('/tmp/deadlift_b64.txt', 'utf-8').trim();
const bench_b64 = 'data:image/png;base64,' + fs.readFileSync('/tmp/bench_press_b64.txt', 'utf-8').trim();
const pull_b64 = 'data:image/png;base64,' + fs.readFileSync('/tmp/pull_up_b64.txt', 'utf-8').trim();
const overhead_b64 = 'data:image/png;base64,' + fs.readFileSync('/tmp/overhead_press_b64.txt', 'utf-8').trim();

// 1. Update Back Squat
fileStr = fileStr.replace(
  /image_base64:\s*'data:image\/svg\+xml;base64,[^']+'/,
  `image_base64: '${squat_b64}'`
);

// 2. Deadlift
fileStr = fileStr.replace(
  /coaching:\s*\[([^\]]+)\],(\s+)\}/g,
  (match, p1, p2) => {
    if (match.includes('Solid neutral-spine pull')) {
      return `coaching: [${p1}],
      annotated_frames: [
        {
          label: 'Rep 1 (Best)', image_base64: '${deadlift_b64}',
          rep_num: 1, side: 'center', is_best: true,
          metrics_shown: ['Spine: 171°', 'Hip:Knee 1.05', 'Score: 84']
        }
      ],${p2}}`;
    }
    // 3. Bench Press
    if (match.includes('Solid tuck and path')) {
      return `coaching: [${p1}],
      annotated_frames: [
        {
          label: 'Rep 1 (Best)', image_base64: '${bench_b64}',
          rep_num: 1, side: 'center', is_best: true,
          metrics_shown: ['Elbow Angle: 82°', 'J-curve: 11.5cm', 'Score: 75']
        }
      ],${p2}}`;
    }
    // 4. Pull-Up
    if (match.includes('Add scapular initiation drills')) {
      return `coaching: [${p1}],
      annotated_frames: [
        {
          label: 'Rep 1 (Best)', image_base64: '${pull_b64}',
          rep_num: 1, side: 'center', is_best: true,
          metrics_shown: ['Elbow ROM: 92°', 'Swing: 4cm', 'Score: 70']
        }
      ],${p2}}`;
    }
    // 5. Overhead Press
    if (match.includes('Strong strict press pattern')) {
      return `coaching: [${p1}],
      annotated_frames: [
        {
          label: 'Rep 1 (Best)', image_base64: '${overhead_b64}',
          rep_num: 1, side: 'center', is_best: true,
          metrics_shown: ['Lockout: +1.2cm', 'Lumbar Ext: 4°', 'Score: 86']
        }
      ],${p2}}`;
    }
    return match;
  }
);

fs.writeFileSync('frontend/src/assessments/strength/exercises.ts', fileStr);
console.log('Successfully updated exercises.ts with actual generated images.');
