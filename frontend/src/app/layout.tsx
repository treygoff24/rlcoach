import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'rlcoach - AI Rocket League Coach',
  description: 'The best AI Rocket League coach. Upload replays, analyze your gameplay, and improve with Claude-powered coaching.',
  keywords: ['Rocket League', 'coach', 'AI', 'replay analysis', 'improvement'],
  authors: [{ name: 'rlcoach' }],
  openGraph: {
    title: 'rlcoach - AI Rocket League Coach',
    description: 'Upload replays, analyze your gameplay, and improve with AI coaching.',
    url: 'https://rlcoach.gg',
    siteName: 'rlcoach',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'rlcoach - AI Rocket League Coach',
    description: 'Upload replays, analyze your gameplay, and improve with AI coaching.',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} bg-gray-950 text-gray-100 antialiased`}>
        {children}
      </body>
    </html>
  );
}
