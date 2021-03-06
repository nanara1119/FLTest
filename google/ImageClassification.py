'''
https://www.tensorflow.org/federated/tutorials/federated_learning_for_image_classification
'''
# %%
from __future__ import absolute_import, division, print_function

import collections
from six.moves import range
import numpy as np

import tensorflow as tf
import tensorflow_federated as tff

import logging
tf.get_logger().setLevel(logging.INFO)

np.random.seed(0)

tf.compat.v1.enable_v2_behavior()

tff.federated_computation(lambda: 'Hello, World!')()

# %% data load
emnist_train, emnist_test = tff.simulation.datasets.emnist.load_data()

print(len(emnist_test.client_ids))
print("train type : {} , test type : {}".format(emnist_train.output_types, emnist_test.output_shapes))

# %%
example_dataset = emnist_train.create_tf_dataset_for_client(emnist_train.client_ids[0])
example_element = iter(example_dataset).next()
print(example_element['label'].numpy())

# %%
from matplotlib import pyplot as plt
plt.imshow(example_element['pixels'].numpy(), cmap='gray', aspect='equal')
plt.grid('off')
_ = plt.show()

# %%
NUM_EPOCHS = 10
BATCH_SIZE = 20
SHUFFLE_BUFFER = 500

def preprocess(dataset):

    d = iter(dataset).next()
    #print(d['label'].numpy())

    def element_fn(element):
        return collections.OrderedDict([
            ('x', tf.reshape(element['pixels'], [-1])),
            ('y', tf.reshape(element['label'], [1]))
        ])

    return dataset.repeat(NUM_EPOCHS).map(element_fn).shuffle(SHUFFLE_BUFFER).batch(BATCH_SIZE)


preprocessed_example_dataset = preprocess(example_dataset)

sample_batch = tf.nest.map_structure(
    lambda x: x.numpy(), iter(preprocessed_example_dataset).next())

print(sample_batch)



# %%
def make_federated_data(client_data, client_ids):
    print(client_ids)
    return [preprocess(client_data.create_tf_dataset_for_client(x)) for x in client_ids]

NUM_CLIENTS = 3

sample_clients = emnist_train.client_ids[0:NUM_CLIENTS]
federated_train_data = make_federated_data(emnist_train, sample_clients)
print(len(federated_train_data), federated_train_data[0])


# %%
def create_compiled_keras_model():
    model = tf.keras.models.Sequential([
        tf.keras.layers.Dense(
            10, activation=tf.nn.softmax, kernel_initializer='zeros', input_shape=(784,))])

    model.compile(
        loss=tf.keras.losses.SparseCategoricalCrossentropy(),
        optimizer=tf.keras.optimizers.SGD(learning_rate=0.1),
        metrics=[tf.keras.metrics.SparseCategoricalAccuracy()])

    return model


# %%
def model_fn():
    keras_model = create_compiled_keras_model()
    return tff.learning.from_compiled_keras_model(keras_model, sample_batch)


# %%
iterative_process = tff.learning.build_federated_averaging_process(model_fn)
print(str(iterative_process.initialize.type_signature))

# %%
state = iterative_process.initialize()
state, metrics = iterative_process.next(state, federated_train_data)
print('round 1, metrics={}'.format(metrics))

# %%
for round_num in range(2, 5):
    state, metrics = iterative_process.next(state, federated_train_data)
    print('round {:2d} , metrics{}'.format(round_num, metrics))

# %%
MnistVariables = collections.namedtuple(
    'MnistVariables', 'weights bias num_examples loss_sum accuracy_sum')


def create_mnist_variables():
    return MnistVariables(
        weights=tf.Variable(
            lambda: tf.zeros(dtype=tf.float32, shape=(784, 10)),
            name='weights',
            trainable=True),
        bias=tf.Variable(
            lambda: tf.zeros(dtype=tf.float32, shape=(10)),
            name='bias',
            trainable=True),
        num_examples=tf.Variable(0.0, name='num_examples', trainable=False),
        loss_sum=tf.Variable(0.0, name='loss_sum', trainable=False),
        accuracy_sum=tf.Variable(0.0, name='accuracy_sum', trainable=False))


def mnist_forward_pass(variables, batch):
    y = tf.nn.softmax(tf.matmul(batch['x'], variables.weights) + variables.bias)
    predictions = tf.cast(tf.argmax(y, 1), tf.int32)

    flat_labels = tf.reshape(batch['y'], [-1])
    loss = -tf.reduce_mean(tf.reduce_sum(
        tf.one_hot(flat_labels, 10) * tf.log(y), reduction_indices=[1]))
    accuracy = tf.reduce_mean(
        tf.cast(tf.equal(predictions, flat_labels), tf.float32))

    num_examples = tf.cast(tf.size(batch['y']), tf.float32)

    variables.num_examples.assign_add(num_examples)
    variables.loss_sum.assign_add(loss * num_examples)
    variables.accuracy_sum.assign_add(accuracy * num_examples)

    return loss, predictions


def get_local_mnist_metrics(variables):
    return collections.OrderedDict([
        ('num_examples', variables.num_examples),
        ('loss', variables.loss_sum / variables.num_examples),
        ('accuracy', variables.accuracy_sum / variables.num_examples)
    ])


@tff.federated_computation
def aggregate_mnist_metrics_across_clients(metrics):
    return {
        'num_examples': tff.federated_sum(metrics.num_examples),
        'loss': tff.federated_mean(metrics.loss, metrics.num_examples),
        'accuracy': tff.federated_mean(metrics.accuracy, metrics.num_examples)
    }


# %%
class MnistModel(tff.learning.Model):

    def __init__(self):
        self._variables = create_mnist_variables()

    @property
    def trainable_variables(self):
        return [self._variables.weights, self._variables.bias]

    @property
    def non_trainable_variables(self):
        return []

    @property
    def local_variables(self):
        return [
            self._variables.num_examples, self._variables.loss_sum,
            self._variables.accuracy_sum
        ]

    @property
    def input_spec(self):
        return collections.OrderedDict([('x', tf.TensorSpec([None, 784],
                                                            tf.float32)),
                                        ('y', tf.TensorSpec([None, 1], tf.int32))])

    #   todo : autograph 설정 해줘야 에러 나지 않음
    @tf.function(autograph=False)
    def forward_pass(self, batch, training=True):
        del training
        loss, predictions = mnist_forward_pass(self._variables, batch)
        return tff.learning.BatchOutput(loss=loss, predictions=predictions)

    #   todo : autograph 설정 해줘야 에러 나지 않음
    @tf.function(autograph=False)
    def report_local_outputs(self):
        return get_local_mnist_metrics(self._variables)

    @property
    def federated_output_computation(self):
        return aggregate_mnist_metrics_across_clients


# %%
class MnistTrainableModel(MnistModel, tff.learning.TrainableModel):

    @tf.function(autograph=False)
    def train_on_batch(self, batch):
        output = self.forward_pass(batch)
        optimizer = tf.train.GradientDescentOptimizer(0.02)
        optimizer.minimize(output.loss, var_list=self.trainable_variables)
        return output


# %%
iterative_process = tff.learning.build_federated_averaging_process(MnistTrainableModel)
state = iterative_process.initialize()

#%%
state, metrics = iterative_process.next(state, federated_train_data)
print('round 1, metrics={}'.format(metrics))

for round_num in range(2, 11) :
    state, metrics = iterative_process.next(state, federated_train_data)
    print('round {:2d}, metrics={}'.format(round_num, metrics))

#%%
'''
    Evaluation
'''
evaluation = tff.learning.build_federated_evaluation(MnistModel)
print(str(evaluation.type_signature))

#%%
train_metrics = evaluation(state.model, federated_train_data)
print(str(train_metrics))

#%%
federated_test_data = make_federated_data(emnist_test, sample_clients)
print(len(federated_test_data), federated_test_data[0])

#%%
test_metrics = evaluation(state.model, federated_test_data)
print(test_metrics)



