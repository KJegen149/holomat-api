import { Scan } from 'lucide-react'
import PhaseStub from '../components/PhaseStub'

export default function Scanner() {
  return (
    <PhaseStub
      phase="4"
      title="Object Scanner"
      description="Computer vision pipeline for scanning physical objects on the mat, using OpenCV contour detection and GPT-4o Vision for identification and dimension estimation."
      icon={Scan}
      capabilities={[
        'Background subtraction for clean object isolation',
        'ChArUco-calibrated pixel → mm dimension conversion',
        'GPT-4o Vision for object identification',
        'Bounding-box dimension estimation in mm',
        'Object library with up to 50 entries (FIFO eviction)',
        'Scan capture and background baseline management',
      ]}
    />
  )
}
