import hashlib
import os
import sys

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
os.environ.setdefault("TF_DETERMINISTIC_OPS", "1")
os.environ.setdefault("TF_CUDNN_DETERMINISTIC", "1")

import numpy as np
import tensorflow as tf

tf.keras.utils.set_random_seed(0)
try:
    tf.config.experimental.enable_op_determinism()
except AttributeError:
    pass
tf.config.threading.set_intra_op_parallelism_threads(1)
tf.config.threading.set_inter_op_parallelism_threads(1)
np.random.seed(0)

def build_model() -> tf.keras.Model:
    init1 = tf.keras.initializers.GlorotUniform(seed=1)
    init2 = tf.keras.initializers.GlorotUniform(seed=2)
    inputs = tf.keras.Input(shape=(64,), dtype=tf.float32)
    x = tf.keras.layers.Dense(32, activation="relu", kernel_initializer=init1)(inputs)
    outputs = tf.keras.layers.Dense(10, activation="softmax", kernel_initializer=init2)(x)
    return tf.keras.Model(inputs, outputs)

def main() -> int:
    n = int(sys.argv[1])
    model = build_model()
    x = tf.fill((8, 64), 0.1)
    h = hashlib.sha256()
    y = model(x, training=False).numpy()
    h.update(y.tobytes())
    print(f"COLD {hashlib.sha256(y.tobytes()).hexdigest()}", flush=True)
    for _ in range(1, n):
        y = model(x, training=False).numpy()
        h.update(y.tobytes())
    print(f"STEADY {h.hexdigest()}", flush=True)
    return 0

if __name__ == "__main__":
    sys.exit(main())
