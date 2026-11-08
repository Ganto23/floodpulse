const NAMES: Record<string, string> = {
  calder_mytholmroyd: "River Calder (Mytholmroyd)",
  cragg_dauber_bridge: "Cragg Brook (Mytholmroyd)",
  aire_armley: "River Aire (Leeds)",
  calder_whalley: "River Calder (Whalley)",
  eden_sheepmount: "River Eden (Carlisle)",
  greta_low_briery: "River Greta (Keswick)",
  wharfe_otley: "River Wharfe (Otley)",
  ribble_samlesbury: "River Ribble (Samlesbury)",
  kent_victoria_bridge: "River Kent (Kendal)",
  derwent_ouse_bridge: "River Derwent (Ouse Bridge)",
};

export const displayName = (slug: string, fallback: string) => NAMES[slug] ?? fallback;
