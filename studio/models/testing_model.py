from .table_base import SimpleTableModel

TESTING_HEADERS = [
    "Test No.","Test Name","Test Description","Lower Limit","Target Value","Upper Limit","Units"
]

class TestingModel(SimpleTableModel):
    def __init__(self, rows=None, parent=None):
        super().__init__(TESTING_HEADERS, rows, parent)
