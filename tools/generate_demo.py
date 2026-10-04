"""Generate a purely synthetic, non-anatomical monochrome CT phantom for Lumina.

No patient data or original notebook images are read. Generated files stay local.
"""
from pathlib import Path
import numpy as np
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

ROOT = Path(__file__).resolve().parents[1]


def phantom(index=24, count=48, size=256):
    y, x = np.mgrid[-1:1:complex(size), -1:1:complex(size)]
    rng = np.random.default_rng(42 + index)
    pixels = np.full((size, size), -1000., dtype=np.float32)
    body = (x/.86)**2 + (y/.79)**2 < 1
    inner = (x/.78)**2 + (y/.70)**2 < 1
    pixels[body] = -90
    pixels[inner] = 35 + rng.normal(0, 4, pixels.shape)[inner]
    scale = .35 + .65*np.sin(np.pi*(index + .5)/count)
    left = ((x+.34)/(.26*scale))**2 + ((y+.05)/(.49*scale))**2 < 1
    right = ((x-.34)/(.26*scale))**2 + ((y+.05)/(.49*scale))**2 < 1
    lungs = (left | right) & inner
    pixels[lungs] = -810 + rng.normal(0, 22, pixels.shape)[lungs]
    # Stylized stripes illustrate grayscale differences, not real vessels.
    strokes = (np.abs(np.sin(27*x + 15*y)) < .045) & lungs
    pixels[strokes] = -150
    core = ((x-.06)/.20)**2 + ((y-.01)/.24)**2 < 1
    pixels[core] = 60
    vertebra = (x/.115)**2 + ((y-.52)/.12)**2 < 1
    pixels[vertebra] = 1050
    marrow = (x/.067)**2 + ((y-.52)/.07)**2 < 1
    pixels[marrow] = 180
    for theta in np.linspace(.2, 2*np.pi-.2, 14):
        rib = (x-.80*np.cos(theta))**2 + (y-.72*np.sin(theta))**2 < .028**2
        pixels[rib & body] = 1200
    return np.rint(pixels).astype(np.int16)


def generate(folder=None, count=48):
    folder = Path(folder) if folder else ROOT/'data'/'demo'
    folder.mkdir(parents=True, exist_ok=True)
    study, series = generate_uid(), generate_uid()
    for index in range(count):
        hu = phantom(index, count)
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = CTImageStorage
        meta.MediaStorageSOPInstanceUID = generate_uid()
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        path = folder/f'synthetic-{index+1:03d}.dcm'
        ds = FileDataset(str(path), {}, file_meta=meta, preamble=b'\0'*128)
        ds.SOPClassUID = CTImageStorage
        ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
        ds.StudyInstanceUID = study
        ds.SeriesInstanceUID = series
        ds.PatientName = 'SYNTHETIC^PHANTOM'
        ds.PatientID = 'NO-PATIENT-DATA'
        ds.SeriesDescription = 'Purely synthetic non-anatomical phantom'
        ds.Modality = 'CT'
        ds.ImageType = ['DERIVED', 'SECONDARY', 'AXIAL']
        ds.RescaleSlope, ds.RescaleIntercept, ds.RescaleType = 1, 0, 'HU'
        ds.Rows, ds.Columns = hu.shape
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = 'MONOCHROME2'
        ds.PixelRepresentation = 1
        ds.BitsAllocated = ds.BitsStored = 16
        ds.HighBit = 15
        ds.PixelSpacing = [1, 1]
        ds.SliceThickness = 2
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.ImagePositionPatient = [-128, -128, 2*index]
        ds.InstanceNumber = index+1
        ds.PixelData = hu.tobytes()
        ds.is_little_endian, ds.is_implicit_VR = True, False
        ds.save_as(path, write_like_original=False)
    return folder


if __name__ == '__main__':
    print('Synthetic phantom generated in', generate())
