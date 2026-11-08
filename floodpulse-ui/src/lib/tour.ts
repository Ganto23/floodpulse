import type { SetName, Variant } from "./types";

/**
 * Guided walkthrough. Every step points at a REAL held-out backtest moment
 * (found by scanning the exported forecasts; see floodpulse-ui/public/data).
 * Numbers in the text are read from that data, not illustrative.
 */
export interface TourStep {
  title: string;
  body: string;
  look?: string;                                   // where to look on screen
  at?: { set: SetName; variant: Variant; gauge: string; time: string };
}

export const TOUR: TourStep[] = [
  {
    title: "What you're looking at",
    body: "Each dot on the map is a river gauge in northern England. The chart at the bottom shows one river. " +
      "The blue line is the measured river level over the past 3 days. At the grey 'now' line we make a forecast " +
      "for the next 24 hours. Nothing here is live: it's a replay of past data the model never trained on.",
    look: "Chart at the bottom: blue = what the river did.",
    at: { set: "2024", variant: "deployed", gauge: "calder_mytholmroyd", time: "2024-12-04 18:00:00+00:00" },
  },
  {
    title: "A catch",
    body: "River Calder, 4 Dec 2024, 18:00. The river is normal (1.35 m). Using that day's real rain forecast, " +
      "FloodPulse (green) climbs past the red alert line. The old model (orange), which only knows the river's " +
      "history, stays below it. The dotted blue line is what really happened: the river crossed the alert line 23 h later.",
    look: "Chart: green crosses the red dashed line; orange doesn't.",
    at: { set: "2024", variant: "deployed", gauge: "calder_mytholmroyd", time: "2024-12-04 18:00:00+00:00" },
  },
  {
    title: "A miss",
    body: "River Ribble, 16 Oct 2024, 03:00. About 21 h later the river rose past its alert line, peaking around " +
      "4.5 m. FloodPulse topped out near 2.1 m: a miss. Across 2024, with the rain forecasts that existed at the " +
      "time, FloodPulse caught 46% of alert-line crossings, usually less than 2 h ahead.",
    look: "Chart: dotted blue shoots up; green stays low.",
    at: { set: "2024", variant: "deployed", gauge: "ribble_samlesbury", time: "2024-10-16 03:00:00+00:00" },
  },
  {
    title: "Storm Babet, with perfect rain",
    body: "Storm Babet, 19 Oct 2023, 05:00, River Calder. Here we give the model the rain that actually fell, a " +
      "best case no real forecast achieves. FloodPulse expects the alert line to be crossed about 22 h out; the river " +
      "crossed it 24 h later.",
    look: "Chart: green crosses the alert line well before 'now + 24 h'.",
    at: { set: "babet", variant: "oracle", gauge: "calder_mytholmroyd", time: "2023-10-19 05:00:00+00:00" },
  },
  {
    title: "Same moment, no rain forecast",
    body: "Same storm, same moment, but now the model only knows rain that has already fallen. No warning. " +
      "That gap is the main finding: the river model works, and better rain forecasts directly buy longer warnings.",
    look: "Chart: green now stays under the alert line.",
    at: { set: "babet", variant: "past", gauge: "calder_mytholmroyd", time: "2023-10-19 05:00:00+00:00" },
  },
  {
    title: "Explore on your own",
    body: "Click any river in the list or on the map. Use ◀ ▶ under the chart to move one step at a time (or drag " +
      "the slider). 'Advanced' shows extra options and statistics. 'Limitations' lists what this can't do.",
  },
];
