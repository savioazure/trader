class spring:
    """
    This class implements a kind of spring that stretches whenever new values
    are higher than its initial position, but alerts whenever those maximum
    levels decrease beyond a given threshold.
    Used to control that from a given point, values always grow and never
    shrink.
    """

    def __init__(self, configuration, starting_point: float):
        self.params = configuration
        self.log = self.params.log

        self.has_position = False
        self.starting_point = starting_point
        self.max_value = self.starting_point
        self.max_shrink = self.params.stop_drop_rate

    def anchor(self, value):
        self.has_position = True
        self.starting_point = value
        self.max_value = self.starting_point
        self.log.debug('Spring anchored at {}'.format(value))

    def release(self):
        self.has_position = False
        self.log.debug('Spring released...')

    def better(self, x: float, y: float) -> bool:
        """
        Depending on whether we're in BEAR or BULL mode, determines if X is
        better than Y. In BEAR mode, X < Y is better, and in BULL mode
        X >= Y is better.
        """
        if self.params.mode == 'bear':
            return x < y
        else:
            return x >= y

    def breaks(self, new_value: float) -> bool:
        if self.has_position is False:
            return False
        if self.better(new_value, self.max_value):
            self.max_value = new_value
            self.log.debug('Stretched abs.max: {:.2f}'.format(self.max_value))
            return False
        else:
            ratio = abs(self.max_value - new_value) / self.max_value
            if ratio > self.max_shrink:
                self.log.debug(
                    'Breaks!! as max({}) - current({}) ratio is {:.2f}'.format(
                        self.max_value, new_value, ratio))
                self.max_value = new_value
                return True
            else:
                return False

    def check(self, action, price, is_failed_action):
        """
        Check if the new price drops significantly, and update positions.

        :param action:     The action decided by the Deep Q-Net
        :param price:      The current price.
        :is_failed_action: Boolean indicating if the action proposed by
                           the RL is feasible or not. If not, the action is
                           considered a failed action. Examples are attempts
                           to purchase shares without budget, or selling
                           non existing actions.

        :return:           The action, possibly modified after check
        """
        if self.breaks(price):
            self.log.debug('! STOP DROP overrides action to SELL')
            # self.log.warn('! STOP DROP overrides action to SELL')
            action = self.params.action.index('sell')

        # Check if action is failed
        if is_failed_action is False:
            if action == self.params.action.index('buy'):
                self.anchor(price)
            elif action == self.params.action.index('sell'):
                self.release()

        return action

    def correction(self, action, environment):
        """
        Check if we have to force operation due to stop drop
        """
        if self.params.stop_drop is True:
            # is this a failed action?
            is_failed_action = environment.portfolio.failed_action(
                action, environment.price_)
            action = self.check(action, environment.price_, is_failed_action)
        return action
