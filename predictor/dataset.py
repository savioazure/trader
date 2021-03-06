from sklearn.model_selection import train_test_split
import pandas as pd
import numpy as np


class Dataset(object):

    X_train = None
    y_train = None
    X_test = None
    y_test = None

    num_testcases = None
    num_samples = None
    num_features = None
    num_frames = None
    data = None
    num_categories = None

    def __init__(self, params):
        super(Dataset, self).__init__()
        self.params = params
        self.log = params.log

    def train_test_split(self, data):
        self.data = data.copy()
        self.num_categories = data.shape[1]
        series = data.copy()
        series_s = series.copy()

        for i in range(self.params.window_size):
            series = pd.concat([series, series_s.shift(-(i + 1))], axis=1)

        series.dropna(axis=0, inplace=True)
        train, test = train_test_split(
            series, test_size=self.params.test_size, shuffle=False)
        self.X_train, self.y_train = self.reshape(np.array(train))
        self.X_test, self.y_test = self.reshape(np.array(test))

        self.log.info('Dataset split in train {} and test {}'.format(
            self.X_train.shape[0], self.X_test.shape[0]))

        return self

    def reshape(self, data):
        num_entries = data.shape[0] * data.shape[1]
        timesteps = self.params.window_size + 1
        num_samples = int((num_entries / self.num_categories) / timesteps)
        train = data.reshape((num_samples, timesteps, self.num_categories))
        X_train = train[:, 0:self.params.window_size, :]
        y_train = train[:, -1, :]
        return X_train, y_train

    def valid_samples(self, x, all=False):
        """
        Given a candidate number for the total number of samples to be considered
        for training and test, this function simply substract the number of
        test cases, predictions and timesteps from it.
        """
        if all is True:
            return x
        return (x - self.num_testcases - self.params.window_size -
                self.params.num_predictions)

    def find_largest_divisor(self, x, all=False):
        """
        Compute a number lower or equal to 'x' that is divisible by the divsor
        passed as second argument. The flag 'all' informs the function whether
        the number of samples can be used as such (all=True) or it must be
        adjusted substracting the number of test cases, predictions and
        num_timesteps from it.
        """
        found = False
        while x > 0 and found is False:
            if self.valid_samples(x, all) % self.params.batch_size is 0:
                found = True
            else:
                x -= 1
        return x

    def adjust(self, raw):
        """
        Given a raw sequence of samples, it determines the correct number of
        samples that can be used, given the amount of test cases requested,
        the timesteps, the nr of predictions, and the batch_size.
        Returns the raw sequence of samples adjusted, by removing the first
        elements from the array until shape fulfills TensorFlow conditions.
        """
        self.num_samples = raw.shape[0]
        self.num_testcases = int(self.num_samples * self.params.test_size)
        new_testshape = self.find_largest_divisor(
            self.num_testcases, all=True)

        self.log.debug('Reshaping TEST from [{}] to [{}]'.format(
            self.num_testcases, new_testshape))

        self.num_testcases = new_testshape

        new_shape = self.find_largest_divisor(raw.shape[0], all=False)

        self.log.debug('Reshaping RAW from [{}] to [{}]'.format(
            raw.shape, raw[-new_shape:].shape))

        new_df = raw[-new_shape:].reset_index().drop(['index'], axis=1)
        self.params['adj_numrows'] = new_df.shape[0]
        self.params['adj_numcols'] = new_df.shape[1]

        # Setup the windowing of the dataset.
        self.num_samples = raw.shape[0]
        self.num_features = raw.shape[1] if len(raw.shape) > 1 else 1
        self.num_frames = self.num_samples - (
                self.params.window_size + self.params.num_predictions) + 1
        self.log.info('Adjusted dataset size from {} -> {}'.format(
            raw.shape[0], new_df.shape[0]))

        return new_df
