import rospy
import numpy as np
import tensorflow as tf
#import itertools
#import sys
#from collections import defaultdict, Counter
#import random
import states
import util as u

# HACKING
# batch_size = 1
#state_size = 4  # 15
#hidden_layer_size = 3
#num_actions = 3
#q_discount = 0.9
#learning_rate = 0.001

def flatten(state):
    return np.asarray(state).reshape(1, -1)

# simple single hidden layer neural net for regressing q value for 3 actions
# based on last 5 sonar readings
# input is 15 element 
class NNQTablePolicy(object):

    def __init__(self, state_size, num_actions, hidden_layer_size):
        self.refresh_params()
        self.build_model(state_size, num_actions, hidden_layer_size )

    def refresh_params(self):
        params = rospy.get_param("q_table_policy")
        print "REFRESH_PARAM\t%s" % params
        self.discount = params['discount']
        self.learning_rate = params['learning_rate']
        self.state_normalisation_squash = params['state_normalisation_squash']

    def build_model(self, state_size, num_actions, hidden_layer_size):
        # input is a sequence of 5 * 3 readings; 5 for last 5 in history, 3 for readings (F, L, R)
        # (i.e. they are just concatted for this version as opposed to treated as a seqeucen)
        self.state = tf.placeholder(dtype = tf.float32, shape = [None, state_size])

        # TODO configure with list representing nodes
        # single layer with no hidden rep
        #self.model_q_values = mlp_layer("out", state, state_size, num_actions)
        # VS
        # one hidden layer
        hidden = self.mlp_layer("h1", self.state, state_size, hidden_layer_size, include_non_linearity=True)
        self.model_q_values = self.mlp_layer("out", hidden, hidden_layer_size, num_actions, include_non_linearity=False)

        # max_a q_value   (recall: target for q table training is r + max_a Q (s') )
        self.max_q_value = tf.reduce_max(self.model_q_values)

        # final target output during training will be the target Q values for the examples
        self.target_q_values = tf.placeholder(dtype = tf.float32, shape = [None, num_actions])

        # train with a squared loss & simple sgd
        # TODO! make self.learning_rate a tensor so we honour changes to it!
        sqrd_loss = tf.pow(self.model_q_values - self.target_q_values, 2)
        self.sgd = tf.train.GradientDescentOptimizer(self.learning_rate).minimize(sqrd_loss)

        # build session
        self.sess = tf.Session()
        self.sess.run(tf.initialize_all_variables())

    def mlp_layer(self, name, input, input_size, output_size, include_non_linearity=False):
        with tf.device("/cpu:0"):  # why is my gpu suddenly borked ?! :/
            with tf.variable_scope(name):
                projection = tf.get_variable("projection", [input_size, output_size])
                bias = tf.get_variable("bias", [1, output_size], initializer=tf.constant_initializer(0.0))
                output = tf.matmul(input, projection) + bias
                return tf.nn.sigmoid(output) if include_non_linearity else output

    def q_values_for(self, state):
        return self.sess.run(self.model_q_values, feed_dict={self.state: state})
    
    def q_values_normalised_for_pick(self, q_values):
        return u.normalised(u.raised(q_values, self.state_normalisation_squash))

    def action_given_state(self, state):
        # TODO: shares a lot with discrete q_table code...
        state = flatten(state)
        print ">>action_given_state; state", state
        # state given as iterable, we want to flatten it to (N,1) array
        q_values = self.q_values_for(state)
        print "q_values", q_values
        normed = self.q_values_normalised_for_pick(q_values[0])
        action = u.weighted_choice(normed)
        print "CHOOSE\t based on state", state, "q_values", q_values, "(normed to", normed, ") => action", action
        return action

    def train(self, state_1, action, reward, state_2):
        # TODO: once this more stable push a bunch of this into the comp graph

        state_1 = flatten(state_1)
        state_2 = flatten(state_2)
        print ">>train; action", action, "reward", reward

        # first do forward pass to get MAX q value for s2
        max_a_s2_q_value = self.sess.run(self.max_q_value, feed_dict={self.state: state_2})

        # from this we can define the desired q value update according to the bellman
        # question;  r + theta * max_a Q(s2)
        updated_q_value = reward + (self.discount * max_a_s2_q_value)
        print "max_a_s2_q_value=", max_a_s2_q_value, "=> updated_q_value", updated_q_value

        # fetch q_table entries for state and clobber the entry for the action
        # with with the bellman updated value. leave other values the same (so their loss is 0)
        # NOTE: since we haven't dont any training yet we could have fetched this _with_
        # the same call as max_s2_q_value
        q_values = self.q_values_for(state_1)
        print "q_values", q_values
        q_values[0][action] = updated_q_value
        print "target q_values", q_values

        # train using this new q_value array
        self.sess.run(self.sgd, feed_dict={self.state: state_1, self.target_q_values: q_values})

        print "updated q_values", self.q_values_for(state_1)

#        print "TRAIN\tstate_1", state_1, "action", action, "reward", reward, "state_2", state_2,\
#            " ... max_a_s2_q_value", max_a_s2_q_value, "updated_q_value", updated_q_value,\
#            "__initial_q_values", __initial_q_values, "target q_values", q_values,\
#            "__updated_q_values", __updated_q_values

    def debug_model(self):
        pass
        #TODO:

    def end_of_episode(self):
        print ">>> end of episode stats"
        self.refresh_params()
