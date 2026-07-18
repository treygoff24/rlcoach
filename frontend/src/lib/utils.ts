const MAP_NAMES: Record<string, string> = {
  Stadium_P: 'DFH Stadium',
  stadium_day_p: 'DFH Stadium (Day)',
  STADIUM_10A_P: 'DFH Stadium',

  EuroStadium_P: 'Mannfield',
  EuroStadium_Night_P: 'Mannfield (Night)',
  EuroStadium_Dusk_P: 'Mannfield (Dusk)',

  Park_P: 'Beckwith Park',
  Park_Night_P: 'Beckwith Park (Night)',
  Park_Snowy_P: 'Beckwith Park (Snowy)',

  TrainStation_P: 'Urban Central',
  TrainStation_Night_P: 'Urban Central (Night)',
  TrainStation_Dawn_P: 'Urban Central (Dawn)',

  UtopiaStadium_P: 'Utopia Coliseum',
  UtopiaStadium_Lux_P: 'Utopia Coliseum',

  NeoTokyo_Standard_P: 'Neo Tokyo',
  NeoTokyo_Arcade_P: 'Neo Tokyo (Arcade)',

  beach_night_p: 'Salty Shores',
  Beach_Night_GRS_P: 'Salty Shores',

  Underwater_GRS_P: 'AquaDome',

  Farm_GRS_P: 'Farmstead',

  CHN_Stadium_P: 'Forbidden Temple',
  CHN_Stadium_Day_P: 'Forbidden Temple (Day)',

  UF_Day_P: 'Champions Field',
  FF_Dusk_P: 'Champions Field (Dusk)',

  mall_day_p: 'Neon Fields',

  cs_day_p: 'Core 707',

  outlaw_p: 'Deadeye Canyon',
  Outlaw_Oasis_P: 'Deadeye Canyon',

  Paname_Dusk_P: 'Sovereign Heights',

  street_p: 'Rivals Arena',

  Labs_4v4_Arena15_Blackout_P: 'Throwback Stadium',
};

export function formatMapName(mapCode: string | null | undefined): string {
  if (!mapCode) return 'Unknown Map';

  if (MAP_NAMES[mapCode]) {
    return MAP_NAMES[mapCode];
  }

  const lowerCode = mapCode.toLowerCase();
  for (const [key, value] of Object.entries(MAP_NAMES)) {
    if (key.toLowerCase() === lowerCode) {
      return value;
    }
  }

  const cleanName = mapCode
    .replace(/_P$/i, '')
    .replace(/_GRS$/i, '')
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2'); // Split camelCase

  return cleanName || 'Unknown Map';
}
