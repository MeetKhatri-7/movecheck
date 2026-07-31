import type { Exercise } from '@/data/types';

export const EXERCISES: Exercise[] = [
  {
    id:1, slug:"knee-to-wall-test", name:"Knee-to-Wall Test", subtitle:"Ankle Dorsiflexion",
    category:"Lower Body", duration:"~5 min", difficulty:"Beginner", color:"#00e5b0",
    description:"Measures how far your knee can travel forward while keeping your heel flat. Key indicator of ankle dorsiflexion restriction.",
    cameraSetup:"Side view · Hip height · 1.5–2 m away",
    checklist:["Heel flat on floor","A4 paper in frame","3 reps each side","Knee in line with 2nd toe","Side view · hip height","Slow controlled movement"],
    refs:[
      { type:"VIDEO", title:"How To Perform", sub:"Ankle Dorsiflexion", tag:"Watch first", guide:null },
      { type:"CAMERA", title:"Camera Setup", sub:"Side view · Hip height · 1.5–2 m away", tag:"Position guide", guide:null },
      { type:"GUIDE", title:"Technique Guide", sub:"Step-by-step instructions", tag:"Read before recording", guide:"1. Position yourself side-on to the camera at hip height.\n2. Place your big toe 10 cm from the wall (use tape).\n3. Keep your heel completely flat on the floor.\n4. Drive your knee forward to touch the wall.\n5. Knee should track in line with your 2nd toe.\n6. Do 3 slow, controlled reps.\n7. Film LEFT side first, then RIGHT side separately." },
      { type:"IMAGE", title:"Exercise Image", sub:"Ankle Dorsiflexion", tag:"Body position", guide:null },
    ],
    uploads:[
      { id:"left",  label:"Left Side",  angle:"Side view · Hip height",  reps:"3 reps" },
      { id:"right", label:"Right Side", angle:"Side view · Hip height",  reps:"3 reps" },
      { id:"front", label:"Front View (optional)", angle:"Front view · Knee height · for valgus", reps:"1 rep each leg", optional:true },
    ],
    result:{ status:'RESTRICTED', score:62, summary:'Asymmetry detected between sides. End-range hold time below target.',
      stats:{ validReps:'15/16', confidence:'87%', sides:'left, right', cameraView:'OK' },
      metrics:[
        { name:'Left Knee Travel', value:'24.5 cm', raw:24.5, target:'≥10', max:40, status:'good' },
        { name:'Right Knee Travel', value:'26.9 cm', raw:26.9, target:'≥10', max:40, status:'good' },
        { name:'Left Tibia Angle', value:'150.0°', raw:150, target:'≥35°', max:180, status:'good' },
        { name:'Right Tibia Angle', value:'124.0°', raw:124, target:'≥35°', max:180, status:'good' },
        { name:'Left Heel Lift', value:'0.0 cm', raw:0, target:'<0.2', max:2, status:'good' },
        { name:'Right Heel Lift', value:'0.0 cm', raw:0, target:'<0.2', max:2, status:'good' },
        { name:'Left End Range Hold', value:'0.4 s', raw:0.4, target:'≥0.5s', max:2, status:'bad' },
        { name:'Right End Range Hold', value:'0.1 s', raw:0.1, target:'≥0.5s', max:2, status:'bad' },
      ],
      bilateral:[
        { name:'Knee Travel', left:24.5, right:26.9, unit:'cm', max:35, asymmetry:2.4 },
        { name:'Tibia Angle', left:150, right:124, unit:'°', max:180, asymmetry:26.0 },
      ],
      coaching:['Left/right knee travel asymmetry is 2.4 cm — prioritise the restricted side.','End range hold time is below target on both sides. Practice pausing at end range.','Ankle mobility is adequate. Focus on end-range control before adding load.'],
    }
  },
  {
    id:2, slug:"seated-hip-rotation-test", name:"Seated Hip Rotation Test", subtitle:"Hip Internal / External Rotation",
    category:"Lower Body", duration:"~5 min", difficulty:"Beginner", color:"#4488ff",
    description:"Assesses rotational range of motion at the hip while seated. Reveals restrictions in internal and external rotation.",
    cameraSetup:"Front view · Knee height · 1–1.5 m away",
    checklist:["Seated on edge of bench/table","Feet freely hanging","3 reps each direction","Knees at 90°","Front view · knee height","Don't lean — rotate only"],
    refs:[
      { type:"VIDEO", title:"How To Perform", sub:"Hip Rotation Test", tag:"Watch first", guide:null },
      { type:"CAMERA", title:"Camera Setup", sub:"Front view · Knee height · 1–1.5 m", tag:"Position guide", guide:null },
      { type:"GUIDE", title:"Technique Guide", sub:"Internal vs external rotation", tag:"Read before recording", guide:"1. Sit on edge of bench — feet must hang freely.\n2. Keep upper body completely still.\n3. Rotate lower leg INWARD (internal rotation).\n4. Return to centre, then rotate OUTWARD (external rotation).\n5. Do not tilt your pelvis or lean your trunk.\n6. Film from the front at knee height.\n7. Film LEFT hip first, then RIGHT hip in separate clips." },
      { type:"IMAGE", title:"Hip Rotation Diagram", sub:"Internal vs external", tag:"Reference", guide:null },
    ],
    uploads:[
      { id:"left", label:"Left Hip", angle:"Front view · Knee height", reps:"3 reps each direction" },
      { id:"right", label:"Right Hip", angle:"Front view · Knee height", reps:"3 reps each direction" },
    ],
    result:{ status:'ADEQUATE', score:71, summary:'Mild internal rotation restriction on the left. External rotation within normal range.',
      stats:{ validReps:'12/12', confidence:'92%', sides:'left, right', cameraView:'OK' },
      metrics:[
        { name:'Left Int. Rotation', value:'32.0°', raw:32, target:'≥35°', max:60, status:'bad' },
        { name:'Right Int. Rotation', value:'38.5°', raw:38.5, target:'≥35°', max:60, status:'good' },
        { name:'Left Ext. Rotation', value:'44.0°', raw:44, target:'≥40°', max:70, status:'good' },
        { name:'Right Ext. Rotation', value:'46.5°', raw:46.5, target:'≥40°', max:70, status:'good' },
      ],
      bilateral:[
        { name:'Internal Rotation', left:32, right:38.5, unit:'°', max:60, asymmetry:6.5 },
        { name:'External Rotation', left:44, right:46.5, unit:'°', max:70, asymmetry:2.5 },
      ],
      coaching:['Left hip internal rotation is slightly restricted — common with prolonged sitting.','Prioritise hip 90/90 stretches and pigeon pose variations for the left side.','External rotation looks good on both sides.'],
    }
  },
  {
    id:3, slug:"thoracic-extension", name:"Thoracic Foam Roller Extension", subtitle:"Thoracic Spine Mobility",
    category:"Upper Body", duration:"~3 min", difficulty:"Beginner", color:"#a855f7",
    description:"Evaluates mid-back extension mobility over a foam roller. Identifies thoracic stiffness limiting overhead reach and posture.",
    cameraSetup:"Side view · Shoulder height · 2 m away",
    checklist:["Foam roller perpendicular to spine","Hips remain on floor","Hold 30 sec","Arms crossed on chest","Side view at shoulder height","Full range of motion"],
    refs:[
      { type:"VIDEO", title:"How To Perform", sub:"Thoracic Extension", tag:"Watch first", guide:null },
      { type:"CAMERA", title:"Camera Setup", sub:"Side view · Shoulder height · 2 m", tag:"Position guide", guide:null },
      { type:"GUIDE", title:"Technique Guide", sub:"Foam roller positioning", tag:"Read before", guide:"1. Place foam roller perpendicular to your spine at mid-back.\n2. Cross arms on chest — do not clasp behind your head.\n3. Keep your hips on the floor throughout the entire movement.\n4. Exhale and allow your upper back to extend over the roller.\n5. Hold the extended position for 30 seconds.\n6. Film from your side at shoulder height." },
      { type:"IMAGE", title:"Roller Placement", sub:"Correct spinal position", tag:"Reference", guide:null },
    ],
    uploads:[
      { id:"all", label:"All Reps", angle:"Side view · Shoulder height", reps:"Hold 30 sec" },
    ],
    result:{ status:'RESTRICTED', score:54, summary:'Significant thoracic extension restriction. May impact overhead mechanics.',
      stats:{ validReps:'1/1', confidence:'89%', sides:'n/a', cameraView:'OK' },
      metrics:[
        { name:'Extension Range', value:'18.0°', raw:18, target:'≥25°', max:45, status:'bad' },
        { name:'Hold Duration', value:'28.0 s', raw:28, target:'≥30s', max:35, status:'bad' },
      ],
      bilateral:[], coaching:['Thoracic extension is restricted — work on pec minor and lat stretching.','Consider thoracic mobilisation drills before overhead pressing.'],
    }
  },
  {
    id:4, slug:"quadruped-rotation", name:"Quadruped Rotation (Thread the Needle)", subtitle:"Thoracic Rotation",
    category:"Upper Body", duration:"~5 min", difficulty:"Beginner", color:"#f59e0b",
    description:"Tests thoracic rotational mobility in quadruped. Identifies restrictions in upper back rotation essential for sport.",
    cameraSetup:"Side view · Hip height · 1.5 m away",
    checklist:["Wrists under shoulders","Knees under hips","3 reps each side","Hips stay level","Side view at hip height","Full reach-through"],
    refs:[
      { type:"VIDEO", title:"How To Perform", sub:"Thread the Needle", tag:"Watch first", guide:null },
      { type:"CAMERA", title:"Camera Setup", sub:"Side view · Hip height · 1.5 m", tag:"Position guide", guide:null },
      { type:"GUIDE", title:"Technique Guide", sub:"Rotation mechanics", tag:"Read before", guide:"1. Start in tabletop — wrists under shoulders, knees under hips.\n2. Lift one hand and thread it under your body as far as possible.\n3. Follow your hand with your eyes and head.\n4. Aim for your shoulder to touch the floor.\n5. Hips must stay perfectly level — no rocking.\n6. Return to start position. Repeat 3 times per side.\n7. Film from the side at hip height." },
      { type:"IMAGE", title:"Movement Pattern", sub:"Thread the needle path", tag:"Reference", guide:null },
    ],
    uploads:[
      { id:"left", label:"Left Side", angle:"Side view · Hip height", reps:"3 reps" },
      { id:"right", label:"Right Side", angle:"Side view · Hip height", reps:"3 reps" },
    ],
    result:{ status:'ADEQUATE', score:68, summary:'Slightly limited rotation on the right side. Left side within normal range.',
      stats:{ validReps:'6/6', confidence:'91%', sides:'left, right', cameraView:'OK' },
      metrics:[
        { name:'Left Rotation Range', value:'48.0°', raw:48, target:'≥45°', max:70, status:'good' },
        { name:'Right Rotation Range', value:'38.0°', raw:38, target:'≥45°', max:70, status:'bad' },
      ],
      bilateral:[{ name:'Rotation Range', left:48, right:38, unit:'°', max:70, asymmetry:10.0 }],
      coaching:['Right thoracic rotation is below target — consider thoracic rotation drills.','Asymmetry of 10° may contribute to mechanics issues.'],
    }
  },
  {
    id:5, slug:"shoulder-rotation-90-90", name:"90/90 Shoulder Rotation Test", subtitle:"Shoulder Internal / External Rotation",
    category:"Upper Body", duration:"~5 min", difficulty:"Intermediate", color:"#ff6b6b",
    description:"Measures shoulder rotational range at 90° abduction. Critical for overhead athletes.",
    cameraSetup:"Axial view · Foot of plinth · Looking down humeral axis",
    checklist:["Arm at 90° abduction","Elbow at 90° flexion","3 reps each side","No trunk side-bend","Axial view","Slow controlled rotation"],
    refs:[
      { type:"VIDEO", title:"How To Perform", sub:"90/90 Shoulder Test", tag:"Watch first", guide:null },
      { type:"CAMERA", title:"Camera Setup", sub:"Axial view · Foot of plinth", tag:"Position guide", guide:null },
      { type:"GUIDE", title:"Technique Guide", sub:"Arm positioning guide", tag:"Read before", guide:"1. Lie supine — keep trunk perfectly still throughout.\n2. Raise your arm to shoulder height (90° abduction).\n3. Bend elbow to 90° — forearm points straight up to start.\n4. Rotate forearm UP as far as possible (external rotation).\n5. Return to 90°, then rotate forearm DOWN (internal rotation).\n6. No trunk movement — isolate the shoulder.\n7. Film from the foot end looking down the arm. 3 reps each direction." },
      { type:"IMAGE", title:"90/90 Position", sub:"Starting position guide", tag:"Reference", guide:null },
    ],
    uploads:[
      { id:"left", label:"Left Shoulder", angle:"Axial view · Foot end", reps:"3 reps" },
      { id:"right", label:"Right Shoulder", angle:"Axial view · Foot end", reps:"3 reps" },
    ],
    result:{ status:'RESTRICTED', score:58, summary:'Internal rotation deficit on dominant side. Classic overhead athlete pattern.',
      stats:{ validReps:'12/12', confidence:'88%', sides:'left, right', cameraView:'OK' },
      metrics:[
        { name:'Left Ext. Rotation', value:'94.0°', raw:94, target:'≥90°', max:120, status:'good' },
        { name:'Right Ext. Rotation', value:'88.0°', raw:88, target:'≥90°', max:120, status:'bad' },
        { name:'Left Int. Rotation', value:'58.0°', raw:58, target:'≥60°', max:90, status:'bad' },
        { name:'Right Int. Rotation', value:'42.0°', raw:42, target:'≥60°', max:90, status:'bad' },
      ],
      bilateral:[
        { name:'External Rotation', left:94, right:88, unit:'°', max:120, asymmetry:6.0 },
        { name:'Internal Rotation', left:58, right:42, unit:'°', max:90, asymmetry:16.0 },
      ],
      coaching:['Significant GIRD on the right.','Total arc of motion appears maintained — monitor for labral stress.','Prioritise posterior capsule and sleeper stretch for the right shoulder.'],
    }
  },
  {
    id:6, slug:"single-leg-glute-bridge", name:"Single-Leg Glute Bridge", subtitle:"Glute Strength & Hip Stability",
    category:"Lower Body", duration:"~5 min", difficulty:"Intermediate", color:"#10b981",
    description:"Evaluates unilateral glute strength and pelvic stability. Identifies side-to-side strength differences.",
    cameraSetup:"Side view · Hip height · 1.5–2 m away",
    checklist:["Foot flat on floor","Other leg fully extended","3 reps each side","Full hip extension at top","Side view at hip height","3 sec hold at top"],
    refs:[
      { type:"VIDEO", title:"How To Perform", sub:"Single-Leg Glute Bridge", tag:"Watch first", guide:null },
      { type:"CAMERA", title:"Camera Setup", sub:"Side view · Hip height · 1.5–2 m", tag:"Position guide", guide:null },
      { type:"GUIDE", title:"Technique Guide", sub:"Hip drive mechanics", tag:"Read before", guide:"1. Lie on your back with one foot flat on the floor.\n2. Extend the other leg straight at about 45° angle.\n3. Drive through your heel and raise your hips.\n4. Reach FULL hip extension at the top — squeeze glutes.\n5. Hold the top position for 3 seconds.\n6. Lower slowly under control. 3 reps per side.\n7. Film from your side at hip height." },
      { type:"IMAGE", title:"Bridge Position", sub:"Top position alignment", tag:"Reference", guide:null },
    ],
    uploads:[
      { id:"right", label:"Right Leg", angle:"Side view · Hip height", reps:"3 reps + 3s hold" },
      { id:"left", label:"Left Leg", angle:"Side view · Hip height", reps:"3 reps + 3s hold" },
    ],
    result:{ status:'ADEQUATE', score:74, summary:'Mild glute strength asymmetry. Pelvic control adequate on both sides.',
      stats:{ validReps:'6/6', confidence:'90%', sides:'right, left', cameraView:'OK' },
      metrics:[
        { name:'Right Hip Extension', value:'178.0°', raw:178, target:'≥170°', max:185, status:'good' },
        { name:'Left Hip Extension', value:'168.0°', raw:168, target:'≥170°', max:185, status:'bad' },
        { name:'Right Hold Duration', value:'3.0 s', raw:3, target:'≥3s', max:5, status:'good' },
        { name:'Left Hold Duration', value:'2.5 s', raw:2.5, target:'≥3s', max:5, status:'bad' },
      ],
      bilateral:[
        { name:'Hip Extension Angle', left:168, right:178, unit:'°', max:185, asymmetry:10.0 },
      ],
      coaching:['Left hip extension slightly below target — focus on glute activation drills.','Add single-leg hip thrusts to address the left side deficit.'],
    }
  },
  {
    id:7, slug:"dead-bug", name:"Dead Bug", subtitle:"Core Stability & Motor Control",
    category:"Core", duration:"~5 min", difficulty:"Intermediate", color:"#8b5cf6",
    description:"Tests core stability and motor control under limb loading. Evaluates spinal neutrality while coordinating opposite limbs.",
    cameraSetup:"Side view · Hip height · 2 m away",
    checklist:["Lower back pressed to floor","Arms up, knees at 90°","4 reps each side — all in one clip","Left arm + right leg first, then right arm + left leg","Side view at hip height","No lower back arch — slow 4-second tempo"],
    refs:[
      { type:"VIDEO", title:"How To Perform", sub:"Dead Bug Exercise", tag:"Watch first", guide:null },
      { type:"CAMERA", title:"Camera Setup", sub:"Side view · Hip height · 2 m", tag:"Position guide", guide:null },
      { type:"GUIDE", title:"Technique Guide", sub:"Motor control pattern", tag:"Read before", guide:"1. Lie on your back with arms pointing straight up.\n2. Raise knees to 90° — hips at 90° as well.\n3. Press your lower back FIRMLY into the floor.\n4. Slowly extend LEFT arm + RIGHT leg simultaneously (4-second count).\n5. Return to start (rest), then extend RIGHT arm + LEFT leg (4-second count).\n6. That is 1 round. Repeat for 4 rounds total (8 movements).\n7. Film ALL reps in one continuous clip from the side at hip height." },
      { type:"IMAGE", title:"Dead Bug Pattern", sub:"Limb coordination diagram", tag:"Reference", guide:null },
    ],
    uploads:[
      { id:"all", label:"All Reps", angle:"Side view · Hip height", reps:"4 rounds (L+R alternating)" },
    ],
    result:{ status:'ADEQUATE', score:76, summary:'Good core stability maintained. Minor lower back compensation detected.',
      stats:{ validReps:'8/8', confidence:'85%', sides:'n/a', cameraView:'OK' },
      metrics:[
        { name:'Lumbar Deviation Avg', value:'4.2°', raw:4.2, target:'<5°', max:15, status:'good' },
        { name:'Max Lumbar Deviation', value:'6.8°', raw:6.8, target:'<5°', max:15, status:'bad' },
        { name:'Rep Consistency', value:'88%', raw:88, target:'≥80%', max:100, status:'good' },
      ],
      bilateral:[],
      coaching:['Lumbar deviation exceeds 5° on 2 out of 8 reps — indicates fatigue.','Focus on maintaining pelvic neutral throughout the full movement.'],
    }
  },
  {
    id:8, slug:"hollow-body-hold", name:"Hollow Body Hold", subtitle:"Anterior Core Strength",
    category:"Core", duration:"~2 min", difficulty:"Intermediate", color:"#ec4899",
    description:"Evaluates anterior core strength and posterior pelvic tilt under limb loading.",
    cameraSetup:"Side view · Knee height · 2 m away",
    checklist:["Lower back pressed to floor","Arms extended overhead","3 x 10 sec hold","Legs at 45° or lower","Side view at knee height","No hip flexor compensation"],
    refs:[
      { type:"VIDEO", title:"How To Perform", sub:"Hollow Body Hold", tag:"Watch first", guide:null },
      { type:"CAMERA", title:"Camera Setup", sub:"Side view · Knee height · 2 m", tag:"Position guide", guide:null },
      { type:"GUIDE", title:"Technique Guide", sub:"Hollow position mechanics", tag:"Read before", guide:"1. Lie on your back with arms extended overhead.\n2. Tuck your pelvis — flatten your lower back to the floor.\n3. Lift your shoulder blades off the floor.\n4. Raise your legs to 45° (or lower if core allows).\n5. Hold the position — breathe normally.\n6. Film a side view at knee height.\n7. Capture the entire hold from start to finish. 3 x 10 sec." },
      { type:"IMAGE", title:"Hollow Position", sub:"Full body alignment", tag:"Reference", guide:null },
    ],
    uploads:[
      { id:"hold", label:"Full Hold", angle:"Side view · Knee height", reps:"3 x 10 sec hold" },
    ],
    result:{ status:'GOOD', score:83, summary:'Strong hollow body position. Leg height well below threshold.',
      stats:{ validReps:'3/3', confidence:'93%', sides:'n/a', cameraView:'OK' },
      metrics:[
        { name:'Hold Duration', value:'10.0 s', raw:10, target:'≥10s', max:15, status:'good' },
        { name:'Leg Height Avg', value:'28.0°', raw:28, target:'<30°', max:60, status:'good' },
        { name:'Lumbar Contact', value:'94%', raw:94, target:'≥90%', max:100, status:'good' },
      ],
      bilateral:[],
      coaching:['Excellent hollow body hold duration and position quality.','Lower back contact maintained for 94% of the hold — very good.'],
    }
  },
  {
    id:9, slug:"plank-shoulder-tap", name:"Plank with Shoulder Tap", subtitle:"Core Stability & Anti-Rotation",
    category:"Core", duration:"~3 min", difficulty:"Intermediate", color:"#06b6d4",
    description:"Tests core stability and anti-rotation strength. Measures ability to resist hip rotation during alternating shoulder taps.",
    cameraSetup:"Front-side view · Hip height · 2 m away",
    checklist:["Wrists under shoulders","Hips level throughout","All reps in one clip","Tap opposite shoulder","Front-side view at hip height","Minimal hip rotation"],
    refs:[
      { type:"VIDEO", title:"How To Perform", sub:"Plank Shoulder Tap", tag:"Watch first", guide:null },
      { type:"CAMERA", title:"Camera Setup", sub:"Front-side view · Hip height · 2 m", tag:"Position guide", guide:null },
      { type:"GUIDE", title:"Technique Guide", sub:"Anti-rotation protocol", tag:"Read before", guide:"1. Start in high plank — wrists under shoulders.\n2. Feet slightly wider than hip width for stability.\n3. Maintain a straight line from head to heel.\n4. Lift one hand and tap the opposite shoulder.\n5. Minimise hip rotation — brace your core hard.\n6. Alternate sides continuously.\n7. Film all reps in one clip from a front-side angle at hip height." },
      { type:"IMAGE", title:"Plank Position", sub:"Alignment reference", tag:"Reference", guide:null },
    ],
    uploads:[
      { id:"all", label:"All Reps", angle:"Front-side view · Hip height", reps:"10 taps each side" },
    ],
    result:{ status:'GOOD', score:80, summary:'Good anti-rotation control. Hip deviation within acceptable range.',
      stats:{ validReps:'20/20', confidence:'86%', sides:'n/a', cameraView:'OK' },
      metrics:[
        { name:'Avg Hip Rotation', value:'6.2°', raw:6.2, target:'<8°', max:20, status:'good' },
        { name:'Max Hip Rotation', value:'10.4°', raw:10.4, target:'<8°', max:20, status:'bad' },
        { name:'Rep Consistency', value:'91%', raw:91, target:'≥80%', max:100, status:'good' },
      ],
      bilateral:[],
      coaching:['Hip rotation slightly exceeds target on high-speed reps.','Focus on pausing for 1 second with each tap to increase control.'],
    }
  },
  {
    id:10, slug:"prone-y-t-w-raise", name:"Prone Y-T-W Raise", subtitle:"Scapular Control & Upper Back",
    category:"Upper Body", duration:"~8 min", difficulty:"Advanced", color:"#f97316",
    description:"Comprehensive assessment of scapular control and posterior rotator cuff across Y, T, and W shapes. Requires two camera angles.",
    cameraSetup:"Camera 1: Overhead · Camera 2: Foot-side at 45° elevation",
    checklist:["Prone on bench or mat","Thumbs up throughout","3 reps per shape (Y, T, W)","Two camera angles required","Overhead + foot-side at 45°","Full range on each shape"],
    refs:[
      { type:"VIDEO", title:"How To Perform (Y-T-W)", sub:"All three shapes explained", tag:"Watch first", guide:null },
      { type:"CAMERA", title:"Dual Camera Setup", sub:"Overhead + foot-side 45°", tag:"Critical — 2 cameras", guide:null },
      { type:"GUIDE", title:"Y-T-W Sequence Guide", sub:"3 shapes × 2 angles = 6 videos", tag:"Read carefully", guide:"Y SHAPE: Arms at ~135° from body, thumbs pointing up. Think of making a Y.\nT SHAPE: Arms straight out to sides at exactly 90°. Think of making a T.\nW SHAPE: Elbows bent 90°, upper arms at shoulder height. Like a W.\n\nFor EACH shape:\n  Camera 1 (Overhead): Mount phone directly above. 3 reps.\n  Camera 2 (Foot-side): Position at 45° from feet, elevated. 3 reps.\n\nTotal videos = 6\nDo NOT mix shapes in one video." },
      { type:"IMAGE", title:"Y-T-W Shapes", sub:"All three positions", tag:"Reference", guide:null },
    ],
    uploads:[
      { id:"y-overhead", label:"Prone Y", angle:"Overhead View", reps:"3 reps", shape:"Y" },
      { id:"y-footside", label:"Prone Y", angle:"Foot-Side View", reps:"3 reps", shape:"Y" },
      { id:"t-overhead", label:"Prone T", angle:"Overhead View", reps:"3 reps", shape:"T" },
      { id:"t-footside", label:"Prone T", angle:"Foot-Side View", reps:"3 reps", shape:"T" },
      { id:"w-overhead", label:"Prone W", angle:"Overhead View", reps:"3 reps", shape:"W" },
      { id:"w-footside", label:"Prone W", angle:"Foot-Side View", reps:"3 reps", shape:"W" },
    ],
    result:{ status:'ADEQUATE', score:65, summary:'Scapular depression weakness on left Y-raise. W pattern shows good lower trap activation.',
      stats:{ validReps:'18/18', confidence:'84%', sides:'bilateral', cameraView:'OK' },
      metrics:[
        { name:'Y Raise — Left Arm', value:'62.0°', raw:62, target:'≥70°', max:100, status:'bad' },
        { name:'Y Raise — Right Arm', value:'74.0°', raw:74, target:'≥70°', max:100, status:'good' },
        { name:'T Raise Symmetry', value:'96%', raw:96, target:'≥90%', max:100, status:'good' },
        { name:'W Elbow Angle', value:'87.0°', raw:87, target:'90°', max:110, status:'good' },
      ],
      bilateral:[
        { name:'Y Raise Angle', left:62, right:74, unit:'°', max:100, asymmetry:12.0 },
      ],
      coaching:['Left lower trapezius weakness detected in Y raise — prioritise prone Y exercise.','T and W patterns are symmetrical — good posterior rotator cuff baseline.'],
    }
  },
];

export const catColors: Record<string, string> = {
  'Lower Body': '#00e5b0',
  'Upper Body': '#4488ff',
  'Core': '#a855f7',
};

export function getExerciseBySlug(slug: string): Exercise | undefined {
  return EXERCISES.find(e => e.slug === slug);
}

export function getExerciseById(id: number): Exercise | undefined {
  return EXERCISES.find(e => e.id === id);
}
