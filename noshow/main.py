# %%
'''
https://www.kaggle.com/joniarroba/noshowappointments

!!!
https://www.kaggle.com/belagoesr/predicting-no-show-downsampling-approach-with-rf
'''

# %%
import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.metrics import confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

import Base.BaseServer as BaseServer

le = LabelEncoder()
server = BaseServer.BaseServer.get_instance()

# %%
df_train = pd.read_csv('noshow/KaggleV2-May-2016.csv')

binary_features = ['Scholarship', 'Hipertension', 'Diabetes', 'Alcoholism', 'SMS_received', 'Gender']
target = ['No-show']
categorical = ['Neighbourhood', 'Handcap']
numerical = ['Age']
dates = ['AppointmentDay', 'ScheduledDay']
Ids = ['PatientId', 'AppointmentID']

# %%
df_train['AppointmentDay'] = pd.to_datetime(df_train['AppointmentDay'])
df_train['ScheduledDay'] = pd.to_datetime(df_train['ScheduledDay'])

df_train['waiting_days'] = (df_train['AppointmentDay'] - df_train['ScheduledDay']).dt.days

df_train = df_train[(df_train['waiting_days'] >= -1) & (df_train['waiting_days'] <= 100)]

df_train.Gender = df_train['Gender'].map({"F": 0, "M": 1})
df_train['No-show'] = df_train['No-show'].map({"No": 0, "Yes": 1})

less_than_100 = ['MORADA DE CAMBURI', 'PONTAL DE CAMBURI', 'ILHA DO BOI', 'ILHA DO FRADE',
                 'AEROPORTO', 'ILHAS OCEÂNICAS DE TRINDADE', 'PARQUE INDUSTRIAL']

#df_train.loc[df_train.Neighbourhood.isin(less_than_100), 'Neighbourhood'] = "OTHERS"

df_train.drop(['PatientId', 'AppointmentID', 'ScheduledDay', 'AppointmentDay', 'Neighbourhood'], axis=1, inplace=True)

#le.fit(df_train['Neighbourhood'].drop_duplicates())
#df_train['Neighbourhood'] = le.transform(df_train['Neighbourhood'])

# %%
y_train = df_train['No-show']
X_train = df_train.drop('No-show', axis=1)

train_stats = X_train.describe()
train_stats = train_stats.transpose()

X_train = (X_train - train_stats['mean'] ) / train_stats['std']

X_train, X_val, y_train, y_val = train_test_split(X_train, y_train, test_size=0.15, shuffle=True)

result = [x for x in y_train if x == 1]
print("total train size : ", len(y_train), " / no :" , (len(y_train) - len(result)), " : yes " ,len(result))

result = [x for x in y_val if x == 1]
print("total test size : ", len(y_val), " / no :" ,  (len(y_val) - len(result)), " : yes " ,len(result))

# %%
def print_cm(y_val, y_pred):
    cm = confusion_matrix(y_val, y_pred)
    print(cm)
    print("accuracy : {}".format(((cm[0][0] + cm[1][1]) / len(X_val)) * 100))

# %%
def build_model():

    model = tf.keras.models.Sequential([
        tf.keras.layers.Dense(units=64, activation=tf.nn.relu, input_dim=9),
        tf.keras.layers.Dense(units=64, activation=tf.nn.relu),
        tf.keras.layers.Dense(1, activation='sigmoid')
    ])
    model.compile(optimizer=tf.keras.optimizers.SGD(learning_rate=0.01),
                  loss=tf.keras.losses.binary_crossentropy,
                  metrics=['accuracy'])


    return model

model = build_model()
# %%
model.fit(X_train, y_train, batch_size=32, epochs=5)

# %%    nn
y_pred = model.predict(X_val)
y_pred = (y_pred > 0.5)

print("result count : ", np.count_nonzero(y_pred == 0), np.count_nonzero(y_pred == 1))
print_cm(y_val, y_pred)

# %%    random forest
from sklearn.ensemble import RandomForestClassifier

forest = RandomForestClassifier(n_estimators=100)
forest.fit(X_train, y_train)
y_pred = forest.predict(X_val)
print("result count : ", np.count_nonzero(y_pred == 0), np.count_nonzero(y_pred == 1))
print_cm(y_val, y_pred)


# %% GradientBoosting
from sklearn.ensemble import GradientBoostingClassifier

gbc = GradientBoostingClassifier(random_state=0)
gbc.fit(X_train, y_train)

y_pred = gbc.predict(X_val)
print("result count : ", np.count_nonzero(y_pred == 0), np.count_nonzero(y_pred == 1))
print_cm(y_val, y_pred)

# %% Support Vector
from sklearn import svm
clf = svm.SVC(gamma=0.001, C = 1)
clf.fit(X_train, y_train)

y_pred = clf.predict(X_val)
print("result count : ", np.count_nonzero(y_pred == 0), np.count_nonzero(y_pred == 1))
print_cm(y_val, y_pred)

# %%
def run_federate(user_number = 3, round_number =2, epoch = 20, batch_size = 10):
    train_list = np.array_split(X_train, user_number+1)
    test_list = np.array_split(y_train, user_number+1)
    print("federate start : user number : {}, total size : {}, each size : {}".format(user_number, len(X_train),
                                                                                      len(train_list[0])))
    local_model = build_model()
    for r in range(round_number):
        local_weight_list = []
        for user in range(user_number):
            print('---------')
            print("round : ", (r + 1), " / user : ", (user+1))
            print('---------')
            server_weight = server.get_weight()
            if server_weight is not None:
                local_model.set_weights(server_weight)
            local_model.fit(train_list[user], test_list[user], epochs=epoch, batch_size=batch_size, verbose=0)
            local_weight_list.append(local_model.get_weights())
        server.update_weight(local_weight_list)
    print("federate end")

    predict_federate(train_list[-1], test_list[-1], X_val, y_val)
    non_federate(train_list[-1], test_list[-1], X_val, y_val)


# %%
def non_federate(x_train, y_train, x_test, y_test ):
    print("non_federate validation start")
    model = build_model()
    model.fit(x_train, y_train, epochs=5, verbose=0)
    result = model.predict(x_test)
    result = (result > 0.5)
    print_cm(y_test, result)
    print("non_federate validation end\n")



# %%
def predict_federate(x_train, y_train, x_test, y_test):
    print("federate validation start")
    model = build_model()
    model.set_weights(server.get_weight())
    model.fit(x_train, y_train, epochs=5, verbose=0)
    result = model.predict(x_test)
    result = (result > 0.5)
    print_cm(y_test, result)
    print("federate validation end")

# %%
run_federate(user_number=10, round_number=100, batch_size=20, epoch=5)

# %%
def test():
    model = build_model()
    model.set_weights(server.get_weight())
    model.fit(X_train, y_train, epochs=5)
    result = model.predict(X_val)
    result = (result > 0.5)
    print_cm(y_val, result)

test()

#%%
server.init_weight()