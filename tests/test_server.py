"""Numerical and HTTP integration checks; synthetic files contain no patient data."""
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

import server


def dicom(path, uid, position, values=None, orientation=None, instance=1, **tags):
    values = np.array([[0, 500], [1000, 2000]], dtype=np.uint16) if values is None else values
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = CTImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = CTImageStorage
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.SeriesInstanceUID = uid
    ds.Modality = "CT"
    ds.Rows, ds.Columns = values.shape
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.PixelRepresentation = int(values.dtype.kind == 'i')
    ds.BitsAllocated = ds.BitsStored = 16
    ds.HighBit = 15
    ds.RescaleSlope = 1
    ds.RescaleIntercept = -1024
    ds.ImageOrientationPatient = orientation or [1, 0, 0, 0, 1, 0]
    ds.ImagePositionPatient = position
    ds.PixelSpacing = [1, 1]
    ds.InstanceNumber = instance
    for key, value in tags.items():
        setattr(ds, key, value)
    ds.PixelData = values.tobytes()
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    ds.save_as(path, write_like_original=False)
    return path


class ViewerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        server.SERIES.clear()
        server.pixels.cache_clear()
        server.image_png.cache_clear()

    def tearDown(self):
        self.temp.cleanup()

    def add(self, **tags):
        path = dicom(self.root / 'slice.dcm', generate_uid(), [0, 0, 0], **tags)
        ids, _ = server.index_paths([path])
        return ids[0]

    def test_oblique_sort_uses_normal_not_patient_z(self):
        uid = generate_uid()
        orientation = [0, 1, 0, 0, 0, 1]
        first = dicom(self.root / 'a.dcm', uid, [20, 0, 0], orientation=orientation, instance=1)
        second = dicom(self.root / 'b.dcm', uid, [10, 0, 0], orientation=orientation, instance=2)
        ids, rejected = server.index_paths([first, second])
        series = server.SERIES[ids[0]]
        self.assertEqual(rejected, 0)
        self.assertEqual(series['records'][0]['path'], second)
        self.assertEqual(series['slice_spacing'], 10)
        self.assertEqual(series['plane'], 'sagittale')
        self.assertEqual(series['labels']['right'], 'P')

    def test_unsigned_and_fractional_rescale_preserved(self):
        sid = self.add(values=np.array([[65535, 3], [5, 7]], dtype=np.uint16), RescaleSlope=.5, RescaleIntercept=-1024.25)
        hu, _, _ = server.pixels(sid, 0)
        self.assertEqual(float(hu[0, 0]), 31743.25)
        self.assertEqual(float(hu[0, 1]), -1022.75)

    def test_each_slice_uses_its_own_calibration(self):
        uid = generate_uid()
        a = dicom(self.root/'a.dcm', uid, [0, 0, 0], RescaleSlope=1)
        b = dicom(self.root/'b.dcm', uid, [0, 0, 1], RescaleSlope=2)
        sid = server.index_paths([b, a])[0][0]
        self.assertEqual(server.pixels(sid, 0)[0][0, 1], -524)
        self.assertEqual(server.pixels(sid, 1)[0][0, 1], -24)

    def test_padding_stays_black_after_monochrome1_inversion(self):
        sid = self.add(values=np.array([[0, 1], [2, 3]], dtype=np.uint16), PixelPaddingValue=0, PhotometricInterpretation='MONOCHROME1', RescaleIntercept=0)
        data = server.image_png(sid, 0, 1.5, 4, False)
        image = np.array(Image.open(io.BytesIO(data)))
        self.assertEqual(image[0, 0], 0)
        self.assertGreater(image[0, 1], image[1, 1])

    def test_dicom_window_width_one_and_linear(self):
        np.testing.assert_array_equal(server.window_pixels(np.array([-.5, 0, 1]), 0, 1), [0, 1, 1])
        np.testing.assert_allclose(server.window_pixels(np.array([-2, 0, 1]), 0, 3), [0, .75, 1])

    def test_pixel_spacing_changes_display_aspect(self):
        sid = self.add(PixelSpacing=[2, 1])
        image = Image.open(io.BytesIO(server.image_png(sid, 0, 0, 1000, False)))
        self.assertEqual(image.size, (1, 2))

    def test_mixed_series_and_stable_identifier(self):
        a = dicom(self.root/'a.dcm', generate_uid(), [0, 0, 0])
        b = dicom(self.root/'b.dcm', generate_uid(), [0, 0, 1])
        ids, _ = server.index_paths([a, b])
        self.assertEqual(len(ids), 2)
        server.SERIES.clear()
        new_ids, _ = server.index_paths([a, b])
        self.assertEqual(ids, new_ids)

    def test_duplicate_and_irregular_spacing_warn(self):
        uid = generate_uid()
        paths = [dicom(self.root/f'{i}.dcm', uid, [0, 0, z]) for i, z in enumerate([0, 1, 1, 5])]
        sid = server.index_paths(paths)[0][0]
        self.assertEqual(len(server.SERIES[sid]['warnings']), 2)

    def test_http_endpoints_and_input_boundaries(self):
        sid = self.add()
        http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        worker = threading.Thread(target=http.serve_forever, daemon=True)
        worker.start()
        base = f'http://127.0.0.1:{http.server_port}'
        try:
            metadata = json.load(urlopen(base+'/api/series'))
            self.assertEqual(metadata[0]['count'], 1)
            self.assertNotIn('records', metadata[0])
            self.assertNotIn('PatientName', str(metadata))
            guide = urlopen(base+'/guide').read().decode('utf-8')
            self.assertIn('Lumina — Guide utilisateur', guide)
            self.assertIn('/guide-assets/fenetres-ct.png', guide)
            self.assertIn('unités Hounsfield', urlopen(base+'/guide.md').read().decode('utf-8'))
            self.assertEqual(urlopen(base+'/guide-assets/fenetres-ct.png').headers['Content-Type'], 'image/png')
            png = urlopen(base+f'/api/image?series={sid}&index=0').read()
            self.assertTrue(png.startswith(b'\x89PNG'))
            for endpoint, code in [(f'/api/image?series={sid}&index=-1', 400), (f'/api/image?series={sid}&width=0', 400), (f'/api/image?series={sid}&center=nan', 400), ('/api/image?series=unknown', 404), ('/../server.py', 404)]:
                with self.assertRaises(HTTPError) as exc:
                    urlopen(base+endpoint)
                self.assertEqual(exc.exception.code, code)
            with self.assertRaises(HTTPError) as exc:
                urlopen(Request(base+'/api/series', headers={'Origin':'https://example.com'}))
            self.assertEqual(exc.exception.code, 403)
            # Import through the real HTTP multipart route; redirect storage to this fixture directory.
            old_root = server.ROOT
            server.ROOT = self.root
            try:
                payload = (b'--boundary\r\nContent-Disposition: form-data; name="files"; filename="slice.dcm"\r\nContent-Type: application/dicom\r\n\r\n' + (self.root/'slice.dcm').read_bytes() + b'\r\n--boundary--\r\n')
                imported = json.load(urlopen(Request(base+'/api/import', data=payload, headers={'Content-Type':'multipart/form-data; boundary=boundary'})))
                self.assertEqual(imported['rejected'], 0)
                self.assertEqual(imported['ids'][0], sid)
            finally:
                server.ROOT = old_root
        finally:
            http.shutdown()
            http.server_close()
            worker.join()


if __name__ == '__main__':
    unittest.main()
