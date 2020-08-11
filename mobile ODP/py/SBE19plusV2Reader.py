import logging
import os
import sys

import arrow


class SBE19plusV2Reader:

    """
    This class
    """

    def __init__(self, **kwargs):
        super().__init__()

        self.raw_data = None
        self.line_count = None
        self.data_start = None
        self.sampling_frequency = 4
        self.casts = dict()

    def load_file(self, data_file):
        """
        Method to load the file into memory
        :param data_file: *.hex SBE 19plusV2 data file
        :return:
        """
        try:

            f = open(data_file, 'r')
            self.line_count = sum(bl.count("\n") for bl in self.blocks(f))
            self.raw_data = f.read()
            f.close()

        except Exception as ex:

            logging.error(f"Error reading the data file: {ex}")

    def parse_header(self):
        """
        Method to parse a *.hex file that contains raw frequencies and voltages in hexadecimal format

        Reference:  Seabird_19plusV2_013.pdf manual, p. 75,
                    https://www.seabird.com/asset-get.download.jsa?id=54627862329

        :return:
        """
        if self.raw_data is None:
            logging.error(f"Raw data has not been loaded, please run the load_file method first")
            return

        found_model = False

        for i, line in enumerate(self.raw_data.splitlines()):

            # Parse where the data starts
            if line.startswith("*END*"):
                self.data_start = i + 1
                break

            # Parse the cast information (start times, samples start/end)
            if line.startswith("* cast "):
                try:
                    cast = line.strip("* cast")
                    cast_items = cast.split("samples")
                    cast_metrics = cast_items[1].split(",")
                    cast_start = int(cast_metrics[0].split("to")[0].strip())
                    cast_end = int(cast_metrics[0].split("to")[1].strip())
                    cast_num = cast_items[0].split(" ")[0]
                    cast_date_time = arrow.get(cast_items[0].strip(cast_num),
                                               "DD MMM YYYY HH:mm:ss").to(tz="US/Pacific")
                    cast_dict = dict()
                    cast_dict['cast num'] = cast_num
                    cast_dict['date time'] = cast_date_time
                    cast_dict['sample start'] = cast_start
                    cast_dict['sample end'] = cast_end
                    self.casts[cast_num] = cast_dict

                    logging.info(f"cast = {cast}")

                except Exception as ex:

                    logging.error(f"error occurred")

            # Parse the calibration coefficients

    def parse_data(self):
        """
        Method to parse the actual hex data
        :return:
        """
        pass

    @staticmethod
    def blocks(files, size=65536):
        while True:
            b = files.read(size)
            if not b:
                files.seek(0)
                break
            yield b


if __name__ == "__main__":

    # Setup Logging Format/etc.
    log_fmt = '%(levelname)s:%(filename)s:%(lineno)s:%(message)s'
    logging.basicConfig(format=log_fmt, level=logging.INFO, stream=sys.stdout)

    path = r"C:\Todd.Hay\Code\SeabirdProcessing\data\sbe19plusV2\2018_CTD_Excalibur"
    filename = r"PORT_CTD5048_DO1505CT1460Op302_HaulsPPtest1_07May2018.hex"
    data_file = os.path.join(path, filename)
    sbe = SBE19plusV2Reader()
    sbe.load_file(data_file=data_file)
    sbe.parse_header()

    logging.info(f"line_count = {sbe.line_count}")
    # logging.info(f"raw_data = {sbe.raw_data}")

    logging.info(f"data start = {sbe.data_start}")
    logging.info(f"casts = {sbe.casts}")