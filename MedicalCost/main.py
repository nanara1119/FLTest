'''
    https://www.kaggle.com/hely333/eda-regression
'''
# %%    load csv
import warnings

import matplotlib.pyplot as plt
import pandas as pd
from sklearn import preprocessing, linear_model, metrics
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score, mean_squared_error
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import PolynomialFeatures, StandardScaler

from Base.BaseFedClient import BaseFedClient

warnings.filterwarnings('ignore')
data = pd.read_csv('../MedicalCost/insurance.csv')

# %%    데이터 확인
print(data.head())
print(data.isnull().sum())

data = data.dropna()

# %%    value change by on-hot-encoding
from sklearn.preprocessing import LabelEncoder

le = LabelEncoder()

# gender, female - 0, male - 1
le.fit(data.sex.drop_duplicates())
data.sex = le.transform(data.sex)

# is smoker, 1 - yes, 0 - no
le.fit(data.smoker.drop_duplicates())
data.smoker = le.transform(data.smoker)

# region, SW - 3 , SE - 2, NW -1, NE - 0
le.fit(data.region.drop_duplicates())
data.region = le.transform(data.region)

print(data)

# %%
train_dataset = data.sample(frac=0.8, random_state=0)
test_dataset = data.drop(train_dataset.index)

# sns.pairplot(train_dataset[["age", "bmi", "charges"]], diag_kind="kde")
# plt.show()

train_stats = train_dataset.describe()
train_stats.pop('charges')
train_stats = train_stats.transpose()
print(train_stats)

train_labels = train_dataset.pop('charges')
test_labels = test_dataset.pop('charges')

# %%
def norm(x):
    return (x - train_stats['mean']) / train_stats['std']

normed_train_data = norm(train_dataset)
#normed_train_data = train_dataset
normed_test_data = norm(test_dataset)
#normed_test_data = test_dataset

print(normed_train_data)

# %%
def show_graph(label, predict):
    plt.scatter(label, predict)
    plt.xlabel('True Values [MPG]')
    plt.ylabel('Predictions [MPG]')
    plt.axis('equal')
    plt.axis('square')
    plt.xlim([0, plt.xlim()[1]])
    plt.ylim([0, plt.ylim()[1]])
    _ = plt.plot([-100, 100], [-100, 100])
    plt.show()


# %%    LinearRegression

x = data.drop(['charges'], axis=1)
y = data.charges

x_train, x_test, y_train, y_test = train_test_split(x, y, random_state=0)

lr = LinearRegression().fit(x_train, y_train)

y_train_pred = lr.predict(x_train)
y_test_pred = lr.predict(x_test)

print('score : ', lr.score(x_test, y_test))
show_graph(y_test, y_test_pred)
print("mae : ", metrics.mean_absolute_error(y_test, y_test_pred))


# %%    LinearRegression region delete
'''
X = data.drop(['charges', 'region'], axis=1)
Y = data.charges

quad = PolynomialFeatures(degree=2)
x_quad = quad.fit_transform(X)

X_train, X_test, Y_train, Y_test = train_test_split(x_quad, Y, random_state=0)

plr = LinearRegression().fit(X_train, Y_train)

Y_train_pred = plr.predict(X_train)
Y_test_pred = plr.predict(X_test)
print(plr.score(X_test, Y_test))
'''

# %%    RandomForest
'''
forest = RandomForestRegressor(n_estimators=100,
                               criterion='mse',
                               random_state=1,
                               n_jobs=-1)
forest.fit(normed_train_data, train_labels)

forest_train_pred = forest.predict(normed_train_data)
forest_test_pred = forest.predict(normed_test_data)

print(len(forest_test_pred), len(test_labels))

print('MSE train data: %.3f, MSE test data: %.3f' % (
    mean_squared_error(train_labels, forest_train_pred),
    mean_squared_error(test_labels, forest_test_pred)))
print('R2 train data: %.3f, R2 test data: %.3f' % (
    r2_score(train_labels, forest_train_pred),
    r2_score(test_labels, forest_test_pred)))
    '''

# %%
fedClient = BaseFedClient()

fedClient.set(normed_train_data, train_labels, normed_test_data, test_labels, epoch=300, batch_size=50)
history = fedClient.run_federate()

# %%
result = fedClient.run_predict()
show_graph(test_labels, result)

# %%
fedClient.run_evaluate()

#%%
plt.scatter(test_labels, result, c='blue', label='fedrate' )
plt.legend()
plt.scatter(y_test, y_test_pred, c='red', label = 'lr')
plt.legend()
plt.show()

