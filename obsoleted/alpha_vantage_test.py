from alpha_vantage.timeseries import TimeSeries
import matplotlib.pyplot as plt

#f = open('key.txt', 'r')
#key = f.read()
#f.close()
key = 'MOVR6WEWYNSEQ7QU'

ts = TimeSeries(key=key, output_format='pandas')
data, meta_data = ts.get_intraday(symbol='MSFT', interval='1min', outputsize='full')
data['4. close'].plot()
plt.title('Intraday Times Series for the MSFT stock (1 min)')
plt.show()

