/** Display names: river + location. */
const NAMES: Record<string, [string, string]> = {
  calder_mytholmroyd: ["River Calder", "Mytholmroyd"],
  cragg_dauber_bridge: ["Cragg Brook", "Mytholmroyd"],
  aire_armley: ["River Aire", "Armley, Leeds"],
  calder_whalley: ["River Calder", "Whalley"],
  eden_sheepmount: ["River Eden", "Sheepmount, Carlisle"],
  greta_low_briery: ["River Greta", "Low Briery, Keswick"],
  wharfe_otley: ["River Wharfe", "Otley"],
  ribble_samlesbury: ["River Ribble", "Samlesbury"],
  kent_victoria_bridge: ["River Kent", "Victoria Bridge, Kendal"],
  derwent_ouse_bridge: ["River Derwent", "Ouse Bridge"],
};

export const nameParts = (slug: string, fallback: string): [string, string] => NAMES[slug] ?? [fallback, ""];
export const displayName = (slug: string, fallback: string) => {
  const [river, place] = nameParts(slug, fallback);
  return place ? `${river} · ${place}` : river;
};
