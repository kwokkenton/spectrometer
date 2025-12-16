import numpy as np
import pandas as pd
from scipy.interpolate import CubicSpline, interp1d

wavelengths_nm = np.array([405, 425, 450, 475, 515, 555, 550, 600, 640, 690, 745, 855])


class Database:
    def __init__(self, limit=0, limit_end = None):
        self.templates = []
        self.targets = []
        self.limit = limit
        self.limit_end = limit_end
    
    def add(self, x, y):
        self.templates.append(x)
        self.targets.append(y)
        return
    
    def search(self, x):
        x = x[self.limit:self.limit_end]
        return self.targets[np.argmin(np.linalg.norm(np.array(self.templates)[:,self.limit:self.limit_end]- x, axis=1))]
    
    def __len__(self):
        return len(self.targets)
    
def synthesise_absorbance(splines, c):
    return np.array([s(c) for s in splines])

def populate_db(juices, db, data, mode = 'spline'):
    for j in juices:
        splines = []
        for w in range(len(wavelengths_nm)):
            concs = data[j][0]
            pts = [i[w] for i in data[j][1]]
            if mode == 'spline':
                spline = CubicSpline(concs, pts)
            else:
                spline = interp1d(concs, pts)
            splines.append(spline)

        for idx, conc in enumerate(np.linspace(data[j][0].min(), data[j][0].max(), 21)):
            t = synthesise_absorbance(splines, conc)
            db.add(t, (j,conc))
    return db

def compute_absorbance(arr):
    return np.clip(-np.log10(arr), 0, 5)

def compute_data(df):
    df = pd.read_csv('spectrum_data.csv', delimiter=',')
    juices = list(df.Juice.unique())[1:]

    blank = df.loc[df.Juice == 'Water'].iloc[:, :12].values.mean(axis=0)
    blank_std = df.loc[df.Juice == 'Water'].iloc[:, :12].values.std(axis=0)

    data = {}

    for i, j in enumerate(juices):
        sums = []
        concentrations = []
        yerrs = []

        for c in sorted(df['Concentration [%]'].unique()):
            values = df.loc[(df.Juice == j) & (df['Concentration [%]'] == c)].iloc[:, :12].values
            if len(values) > 0:
                concentrations.append(int(c))
                mean = values.mean(axis=0)
                std = values.std(axis=0)
                mean_norm = mean/blank
                std_norm = std/blank
                yerr = np.clip(np.sqrt((0.5 / mean)**2 + (blank_std/blank)**2)/np.log(10), 0, 1)
                sums.append(mean_norm)
                yerrs.append(yerr)

        concentrations = np.array(concentrations)
        yerrs = np.array(yerrs)

        absorbances = compute_absorbance(sums)
        data[j] = concentrations, absorbances, yerrs
    return juices, data

def make_db():
    df = pd.read_csv('spectrum_data.csv', delimiter=',')
    db = Database(limit=2, limit_end=-1)
    juices, data = compute_data(df)
    db = populate_db(juices, db, data)  
    return db