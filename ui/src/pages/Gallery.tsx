import { Image } from 'lucide-react'
import PhaseStub from '../components/PhaseStub'

export default function Gallery() {
  return (
    <PhaseStub
      phase="6"
      title="Gallery"
      description="SMB-watched gallery for ingesting images from the network share, with Cloudflare R2 storage, D1 database, and AI-powered 3D model generation."
      icon={Image}
      capabilities={[
        'Samba share file watcher (HEIC / PNG / JPG / WEBP)',
        'Automatic HEIC → JPEG conversion on ingest',
        'Cloudflare R2 upload and CDN delivery',
        'D1 database for gallery metadata',
        'Meshy AI image-to-3D model generation',
        'SVG recreation via LLM',
      ]}
    />
  )
}
