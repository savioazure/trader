import random
import time
from collections import deque

import numpy as np
from keras.callbacks import TensorBoard

from common import Common
from environment import Environment
from rl_nn import RL_NN


class Agent(Common):
    configuration = None
    tensorboard = None
    memory = deque(maxlen=20000)

    def __init__(self, configuration):
        self.params = configuration
        self.display = self.params.display
        self.nn = RL_NN(self.params)
        self.model = None
        self.callback_args = {}
        if self.params.tensorboard is True:
            self.tensorboard = TensorBoard(
                log_dir=self.params.tbdir,
                histogram_freq=0, write_graph=True, write_images=False)
            self.callback_args = {'callbacks': self.tensorboard}

    def q_load(self,
               env: Environment,
               display_strategy: bool = False) -> list:
        """
        Load an strategy to follow over a given environment, using RL,
        and acts following the strategy defined on it.
        :type env: Environment
        :param display_strategy:
        """
        # create the Keras model and learn, or load it from disk.
        self.model = self.nn.load_model(self.params.model_file,
                                        self.params.weights_file)

        # Extract the strategy matrix from the model.
        strategy = self.get_strategy()
        if display_strategy:
            self.display.strategy(self,
                                  env,
                                  self.model,
                                  self.params.num_states,
                                  strategy)
        return strategy

    def q_learn(self,
                env: Environment,
                fresh_model: bool = True,
                display_strategy: bool = False,
                do_plot: bool = False) -> list:
        """
        Learns an strategy to follow over a given environment,
        using RL.
        :type env: Environment
        :param fresh_model: if False, it does not create the NN from scratch,
            but, it uses the one previously loaded.
        :param display_strategy:
        :type do_plot: bool
        """
        start = time.time()
        # create the Keras model and learn, or load it from disk.
        if fresh_model is True:
            self.model = self.nn.create_model()
        avg_rewards, avg_loss, avg_mae = self.reinforce_learn(env)

        # display anything?
        if do_plot is True and self.params.load_model is False:
            self.display.plot_metrics(avg_loss, avg_mae, avg_rewards)

        # Extract the strategy matrix from the model.
        strategy = self.get_strategy()
        if display_strategy:
            self.display.strategy(self,
                                  env,
                                  self.model,
                                  self.params.num_states,
                                  strategy)

        self.log('Time elapsed: {}'.format(
            self.params.display.timer(time.time() - start)))
        return strategy

    def reinforce_learn(self, env: Environment):
        """
        Implements the learning loop over the states, actions and strategies
        to learn what is the sequence of actions that maximize reward.
        :param env: the environment
        :return:
        """
        # now execute the q learning
        avg_rewards = []
        avg_loss = []
        avg_mae = []
        last_avg: float = 0.0
        start = time.time()
        epsilon = self.params.epsilon

        # Loop over 'num_episodes'
        for step_num in range(self.params.num_episodes):
            state = env.reset()
            self.display.rl_train_report(step_num, avg_rewards, last_avg, start)
            done = False
            sum_rewards = 0
            sum_loss = 0
            sum_mae = 0
            episode_step = 0
            while not done:
                # Decide whether generating random action or predict most
                # likely from the give state.
                action = self.epsilon_greedy(epsilon, state)

                # Send the action to the environment and get new state,
                # reward and information on whether we've finish.
                new_state, reward, done, _ = env.step(action)
                self.memory.append((state, action, reward, new_state, done))

                # loss, mae = self.step_learn(state, action, reward, new_state)
                if episode_step % self.params.train_steps and \
                        episode_step > self.params.start_steps:
                    loss, mae = self.minibatch_learn(self.params.batch_size)

                    # Update states and metrics
                    state = new_state
                    sum_rewards += reward
                    sum_loss += loss
                    sum_mae += mae

                episode_step += 1

            avg_rewards.append(sum_rewards / self.params.num_episodes)
            avg_loss.append(sum_loss / self.params.num_episodes)
            avg_mae.append(sum_mae / self.params.num_episodes)

            # Batch Replay
            if self.params.experience_replay is True:
                if len(self.memory) > self.params.exp_batch_size:
                    self.experience_replay()

            # Epsilon decays here
            if epsilon >= self.params.epsilon_min:
                epsilon *= self.params.decay_factor

        return avg_rewards, avg_loss, avg_mae

    def epsilon_greedy(self, epsilon, state):
        """
        Epsilon greedy routine
        :param epsilon: current value of epsilon after applying decaying f.
        :param state: current state
        :return: action predicted by the network
        """
        if np.random.random() < epsilon:
            action = np.random.randint(
                0, self.params.num_actions)
        else:
            action = self.predict(state)
        return action

    def step_learn(self, state, action, reward, new_state):
        """
        Fit the NN model to predict the action, given the action and
        current state.
        :param state:
        :param action:
        :param reward:
        :param new_state:
        :return: the loss and the metric resulting from the training.
        """
        target = reward + self.params.gamma * self.predict_value(
            new_state)
        target_vec = self.model.predict(self.onehot(state))[0]
        target_vec[action] = target

        history = self.model.fit(
            self.onehot(state),
            target_vec.reshape(-1, self.params.num_actions),
            epochs=1, verbose=0, **self.callback_args
        )
        return history.history['loss'][0], \
               history.history['mean_absolute_error'][0]

    def minibatch_learn(self, batch_size):
        """
        MiniBatch Learning routine.
        :param batch_size:
        :return: loss and mae
        """
        mem_size = len(self.memory)
        if mem_size < batch_size:
            return 0.0, 0.0

        mini_batch = np.empty(shape=(0, 5), dtype=np.int32)
        for i in range(mem_size - batch_size - 1, mem_size - 1):
            mini_batch = np.append(
                mini_batch,
                np.asarray(self.memory[i]).astype(int).reshape(1, -1),
                axis=0)

        nn_input = np.empty((0, self.params.num_states), dtype=np.int32)
        nn_output = np.empty((0, self.params.num_actions))
        for state, action, reward, next_state, done in mini_batch:
            target = reward
            if not done:
                target = reward + self.params.gamma * self.predict_value(
                    next_state)
            nn_input = np.append(nn_input, self.onehot(state), axis=0)
            labeled_output = self.model.predict(self.onehot(state))[0]
            labeled_output[action] = target
            y = labeled_output.reshape(-1, self.params.num_actions)
            nn_output = np.append(nn_output, y, axis=0)

        # h = self.model.train_on_batch(
        #     nn_input, nn_output)
        # return h[0], h[1]
        h = self.model.fit(
            nn_input, nn_output,
            epochs=1, verbose=0, batch_size=batch_size,
            **self.callback_args)
        return h.history['loss'][0], h.history['mean_absolute_error'][0]

    def experience_replay(self):
        """
        Primarily from: https://github.com/edwardhdlu/q-trader
        :return: None
        """
        mini_batch = random.sample(self.memory,
                                   self.params.exp_batch_size)
        for state, action, reward, next_state, done in mini_batch:
            target = reward
            if not done:
                target = reward + self.params.gamma * self.predict_value(
                    next_state)
            target_vec = self.model.predict(self.onehot(state))[0]
            target_vec[action] = target
            self.model.fit(
                self.onehot(state),
                target_vec.reshape(-1, self.params.num_actions),
                epochs=1, verbose=0,
                **self.callback_args)

    def onehot(self, state: int) -> np.ndarray:
        return np.identity(self.params.num_states)[state:state + 1]

    def predict(self, state) -> int:
        return int(
            np.argmax(
                self.model.predict(
                    self.onehot(state))))

    def predict_value(self, state):
        return np.max(self.model.predict(self.onehot(state)))

    def get_strategy(self):
        """
        Get the defined strategy from the weights of the model.
        :return: strategy matrix
        """
        strategy = [
            np.argmax(
                self.model.predict(self.onehot(i))[0])
            for i in range(self.params.num_states)
        ]
        return strategy

    def simulate(self, environment, strategy):
        """
        Simulate over a dataset, given a strategy and an environment.
        :param environment:
        :param strategy:
        :return:
        """
        done = False
        total_reward = 0.
        self.params.debug = True
        state = environment.reset()
        while not done:
            action = environment.decide_next_action(state, strategy)
            next_state, reward, done, _ = environment.step(action)
            total_reward += reward
            state = next_state
        self.params.display.summary(environment.portfolio, do_plot=True)
