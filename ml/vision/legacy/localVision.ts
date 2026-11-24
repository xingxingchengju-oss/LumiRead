import {
  FaceLandmarker,
  FilesetResolver,
  GestureRecognizer,
} from "@mediapipe/tasks-vision";
import { confirmedVictory, eyeTilt, type View } from "./sensors";

export async function loadVision(view: View, centerSearch = false) {
  const files = await FilesetResolver.forVisionTasks("/vision/wasm");
  if (view === "user") {
    const face = await FaceLandmarker.createFromOptions(files, {
      baseOptions: {
        modelAssetPath: "/vision/face_landmarker.task",
        delegate: "CPU",
      },
      runningMode: "VIDEO",
      numFaces: 1,
    });
    return {
      read(canvas: HTMLCanvasElement, now: number, _video?: HTMLVideoElement) {
        const eyes = face.detectForVideo(canvas, now).faceLandmarks[0];
        return {
          tilt: eyeTilt(eyes?.[33], eyes?.[263], canvas.width, canvas.height),
          victory: false,
          handVisible: false,
        };
      },
      close: () => face.close(),
    };
  }
  const model = await GestureRecognizer.createFromOptions(files, {
    baseOptions: {
      modelAssetPath: "/vision/gesture_recognizer.task",
      delegate: "CPU",
    },
    runningMode: "VIDEO",
    numHands: 1,
  });
  const crop = document.createElement("canvas");
  const context = crop.getContext("2d");
  let centered = false,
    misses = 0;
  return {
    read(canvas: HTMLCanvasElement, now: number, video?: HTMLVideoElement) {
      let input = canvas;
      if (centered && context) {
        const source = video ?? canvas;
        const w = video?.videoWidth ?? canvas.width,
          h = video?.videoHeight ?? canvas.height;
        if (crop.width !== canvas.width || crop.height !== canvas.height) {
          crop.width = canvas.width;
          crop.height = canvas.height;
        }
        // Sample at the original camera resolution before downscaling.
        context.drawImage(
          source,
          w / 4,
          h / 4,
          w / 2,
          h / 2,
          0,
          0,
          crop.width,
          crop.height,
        );
        input = crop;
      }
      const result = model.recognizeForVideo(input, now);
      const top = result.gestures[0]?.[0];
      if (centerSearch) {
        misses =
          top && top.categoryName !== "None" && top.score >= 0.5
            ? 0
            : misses + 1;
        if (misses >= 3) {
          centered = !centered;
          misses = 0;
        }
      }
      return {
        tilt: null,
        handVisible: Boolean(result.landmarks[0]?.length),
        category: top?.categoryName,
        score: top?.score ?? 0,
        victory: confirmedVictory(
          top?.categoryName,
          top?.score ?? 0,
          result.worldLandmarks[0],
        ),
      };
    },
    close: () => model.close(),
  };
}
