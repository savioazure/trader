import numpy as np

from file_io import read_json
from last import last


class Update:

    def __init__(self, configuration, action):
        self.params = configuration
        self.log = self.params.log
        getattr(self, action)()

    def predictions(self):
        """
        Take yesterday's OHLC Closing and predictions to update the preds file
        - Opens the file,
        - checks that date is last working day
        - opens latest forecast file,
        - if there's no file, returns
        - check that latest date doesn't match the one from last working day
        - append a row with the predictions from each network, and the stats
        """
        self.log.info('Updating predictions file: {}'.format(self.params.file))
        preds = read_json(self.params.tmp_predictions)
        ohlc = read_json(self.params.tmp_ohlc)
        if preds is None or ohlc is None:
            self.log.info('No temporary files to be used to update preds.')
            return False

        # Read the preds file to check if last line has already been updated
        last_ohlc_date = ohlc[self.params.tmp_dictionary.date]
        if last.date_is(last_ohlc_date, self.params.file,
                        delimiter=self.params.delimiter):
            self.log.warn(
                'Predictions file already contains entry for date: {}'.format(
                    last_ohlc_date))
            return False

        # Method to compute element-wise difference
        def diff_with(array, value):
            return [abs(array[i] - value) for i in range(len(array))]

        # Method to compute the closest value in array to a given value
        def whois_nearest(array, value: float):
            array = np.asarray(array).astype(np.float32)
            idx = (np.abs(array - value)).argmin()
            return idx

        # Preparation to determine who is the winner network
        close_colname = self.params.tmp_dictionary['close']
        pred_keys = list(preds.keys())
        pred_values = np.around(np.array([preds[k] for k in preds.keys()]),
                                decimals=2)
        # Build the csv row to be added
        csv_row = '{},{}'.format(
            last_ohlc_date, ','.join(map(str, pred_values)))
        csv_row = csv_row + ',{:.2f},{:.2f},{:.2f},{:.2f},{}\n'.format(
            np.mean(pred_values),
            np.mean(diff_with(pred_values, np.mean(pred_values))),
            np.median(pred_values),
            np.mean(diff_with(pred_values, np.median(pred_values))),
            pred_keys[whois_nearest(pred_values, float(ohlc[close_colname]))]
        )

        # Append the row at the end of the file
        with open(self.params.file, 'a') as predictions_file:
            predictions_file.write(csv_row)
            self.log.info(
                'Predictions file UPDATED for date: {}'.format(last_ohlc_date))
        return True

    def forecast(self):
        self.log.info('Updating forecast file: {}'.format(self.params.file))
        # Read the temporary files
        ohlc = read_json(self.params.tmp_ohlc)
        ensemble = read_json(self.params.tmp_forecast)
        indicator = read_json(self.params.tmp_indicator)
        if ohlc is None or ensemble is None or indicator is None:
            self.log.info('NOT updating forecast. Missing files.')
            return False
        self.log.info('Read temporary files')

        # flesh out the CSV row
        forecast_items = [
            ohlc[self.params.tmp_dictionary.date],
            float(ohlc[self.params.tmp_dictionary.close]),
            ensemble[self.params.tmp_dictionary.ensemble],
            indicator[self.params.tmp_dictionary.green],
            indicator[self.params.tmp_dictionary.blue]
        ]
        csv_row = ','.join(map(Update.round2two, forecast_items)) + '\n'

        # Read the forecast file to check if last line has already been updated
        last_ohlc_date = ohlc[self.params.tmp_dictionary.date]
        if last.date_is(last_ohlc_date, self.params.file,
                        delimiter=self.params.delimiter):
            self.log.warn(
                'Forecast file already contains entry for date: {}'.format(
                    ohlc[self.params.tmp_dictionary.date]))
            return False

        # Append the last row, normally
        with open(self.params.file, 'a') as forecast_file:
            forecast_file.write(csv_row)
            self.log.info('Forecast file UPDATED for date: {}'.format(
                ohlc[self.params.tmp_dictionary.date]))

        return True

    @staticmethod
    def round2two(x):
        if type(x) == str:
            return x
        return '{:.2f}'.format(x)
