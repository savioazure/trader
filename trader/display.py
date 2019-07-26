import numpy as np


class Display:

    @staticmethod
    def strategy(trader, env, model, num_states, strategy):
        print('\nStrategy learned')
        strategy_string = "State {{:<{}s}} -> {{:<10s}} {{}}".format(
            env.states.max_len)
        for i in range(num_states):
            print(strategy_string.format(
                env.states.name(i),
                trader.configuration._action_name[strategy[i]],
                model.predict(np.identity(num_states)[i:i + 1])))
        print()