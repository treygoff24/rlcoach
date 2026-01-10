import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatNumber(num: number): string {
  return new Intl.NumberFormat('en-US').format(num);
}

export function formatPercentage(num: number): string {
  return `${(num * 100).toFixed(1)}%`;
}

export function formatDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.floor(seconds % 60);
  return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
}

export function formatDate(date: Date | string): string {
  return new Date(date).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export function formatRelativeTime(date: Date | string): string {
  const now = new Date();
  const then = new Date(date);
  const diffInSeconds = Math.floor((now.getTime() - then.getTime()) / 1000);

  if (diffInSeconds < 60) return 'just now';
  if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)}m ago`;
  if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)}h ago`;
  if (diffInSeconds < 604800) return `${Math.floor(diffInSeconds / 86400)}d ago`;
  return formatDate(date);
}

// Rocket League map internal code to friendly name mapping
const MAP_NAMES: Record<string, string> = {
  // DFH Stadium variants
  Stadium_P: 'DFH Stadium',
  stadium_day_p: 'DFH Stadium (Day)',
  STADIUM_10A_P: 'DFH Stadium',

  // Mannfield (Euro) variants
  EuroStadium_P: 'Mannfield',
  EuroStadium_Night_P: 'Mannfield (Night)',
  EuroStadium_Dusk_P: 'Mannfield (Dusk)',

  // Beckwith Park variants
  Park_P: 'Beckwith Park',
  Park_Night_P: 'Beckwith Park (Night)',
  Park_Snowy_P: 'Beckwith Park (Snowy)',

  // Urban Central variants
  TrainStation_P: 'Urban Central',
  TrainStation_Night_P: 'Urban Central (Night)',
  TrainStation_Dawn_P: 'Urban Central (Dawn)',

  // Utopia Coliseum variants
  UtopiaStadium_P: 'Utopia Coliseum',
  UtopiaStadium_Lux_P: 'Utopia Coliseum',

  // Neo Tokyo variants
  NeoTokyo_Standard_P: 'Neo Tokyo',
  NeoTokyo_Arcade_P: 'Neo Tokyo (Arcade)',

  // Salty Shores / Beach variants
  beach_night_p: 'Salty Shores',
  Beach_Night_GRS_P: 'Salty Shores',

  // AquaDome
  Underwater_GRS_P: 'AquaDome',

  // Farmstead
  Farm_GRS_P: 'Farmstead',

  // Forbidden Temple (Chinese)
  CHN_Stadium_P: 'Forbidden Temple',
  CHN_Stadium_Day_P: 'Forbidden Temple (Day)',

  // Champions Field
  UF_Day_P: 'Champions Field',
  FF_Dusk_P: 'Champions Field (Dusk)',

  // Neon Fields (Mall)
  mall_day_p: 'Neon Fields',

  // Core 707
  cs_day_p: 'Core 707',

  // Deadeye Canyon (Outlaw)
  outlaw_p: 'Deadeye Canyon',
  Outlaw_Oasis_P: 'Deadeye Canyon',

  // Paris
  Paname_Dusk_P: 'Sovereign Heights',

  // Street / Rival Arena
  street_p: 'Rivals Arena',

  // Labs / Throwback
  Labs_4v4_Arena15_Blackout_P: 'Throwback Stadium',
};

export function formatMapName(mapCode: string | null | undefined): string {
  if (!mapCode) return 'Unknown Map';

  // Try exact match first
  if (MAP_NAMES[mapCode]) {
    return MAP_NAMES[mapCode];
  }

  // Try case-insensitive match
  const lowerCode = mapCode.toLowerCase();
  for (const [key, value] of Object.entries(MAP_NAMES)) {
    if (key.toLowerCase() === lowerCode) {
      return value;
    }
  }

  // Try to extract a readable name from the code
  // Remove _P suffix and replace underscores with spaces
  const cleanName = mapCode
    .replace(/_P$/i, '')
    .replace(/_GRS$/i, '')
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2'); // Split camelCase

  return cleanName || 'Unknown Map';
}
