from sqlalchemy import  Column, Integer, Boolean, BigInteger, Double, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship


Base = declarative_base()

# Dimension Table for Platform
class DimPlatform(Base):
    __tablename__ = 'platform'
    id = Column(Integer, primary_key=True)
    platform = Column(String , nullable=False, unique=True)

# Dimension Table for Instruments
class DimInstrument(Base):
    __tablename__ = 'instrument'
    id = Column(Integer, primary_key=True)
    instrument = Column(String , nullable=False, unique=True)
    
# Dimension Table for Timestamps
class DimTime(Base):
    __tablename__ = 'time'
    id = Column(BigInteger, primary_key=True)
    time = Column(DateTime , nullable=False, unique=True)

# Dimension Table for measured Parameters
class DimParameter(Base):
    __tablename__ = 'parameter'
    id = Column(Integer, primary_key=True)
    parameter = Column(String , nullable=False, unique=True)
    
# Dimension Table for measurement Units
class DimUnit(Base):
    __tablename__ = 'unit'
    id = Column(Integer, primary_key=True)
    unit = Column(String , nullable=False, unique=True)

# Dimension Table for acquisition Types
class DimAcquisitionType(Base):
    __tablename__ = 'acquisition_type'
    id = Column(Integer, primary_key=True)
    acquisition_type = Column(String , nullable=False, unique=True)

class DimGeolocation(Base):
    __tablename__ = 'geolocation'
    sample_time_id = Column(BigInteger, primary_key=True)
    platform_id = Column(Integer, primary_key=True)
    instrument_id = Column(Integer, primary_key=True)
    latitude = Column(Double, nullable=False)
    longitude = Column(Double, nullable=False)    
    #sample_time = relationship("DimTime", foreign_keys=[sample_time_id])
    #platform = relationship("DimPlatform", foreign_keys=[platform_id])
    #instrument = relationship("DimInstrument", foreign_keys=[instrument_id])

# Vector table for measurements taken by instruments
class InstrumentMeasurements(Base):
    __tablename__ = 'instrument_measurements'
    id = Column(Integer, primary_key=True)
    instrument_id = Column(Integer, ForeignKey('instrument.id'), nullable=False)
    parameter_id = Column(Integer, ForeignKey('parameter.id'), nullable=False)
    unit_id = Column(Integer, ForeignKey('unit.id'), nullable=False)
    acquisition_type_id = Column(Integer, ForeignKey('acquisition_type.id'), nullable=False)
    platform_id = Column(Integer, ForeignKey('platform.id'), nullable=False)
    
    
    platform = relationship("DimPlatform", foreign_keys=[platform_id])
    instrument = relationship("DimInstrument", foreign_keys=[instrument_id])
    parameter = relationship("DimParameter", foreign_keys=[parameter_id])
    unit = relationship("DimUnit", foreign_keys=[unit_id])
    acquisition_type = relationship("DimAcquisitionType", foreign_keys=[acquisition_type_id])
    __table_args__ = (UniqueConstraint('instrument_id', 'parameter_id', 'unit_id', 'acquisition_type_id', name='uq_instrument_measurements'),)

# Fact Table for measurement Data
  
class FactMeasurement(Base):
    __tablename__ = 'measurement'
    id = Column(BigInteger, primary_key=True)

    # Foreign keys to the DimTime table
    acquisition_time_id = Column(BigInteger, ForeignKey('time.id'), nullable=False)
    instrument_time_id = Column(BigInteger, ForeignKey('time.id'), nullable=True)
    sample_time_id = Column(BigInteger, ForeignKey('time.id'), nullable=False)
    sample_time = Column(DateTime , nullable=True, unique=False)

    # Other foreign keys
    platform_id = Column(Integer, ForeignKey('platform.id'), nullable=False)
    instrument_id = Column(Integer, ForeignKey('instrument.id'), nullable=False)
    parameter_id = Column(Integer, ForeignKey('parameter.id'), nullable=False)
    unit_id = Column(Integer, ForeignKey('unit.id'), nullable=False)
    acquisition_type_id = Column(Integer, ForeignKey('acquisition_type.id'), nullable=False)

    value = Column(Double, nullable=False)
    string = Column(String(100), nullable=True)

    # EXPLICIT SAMPLE_TIME COLUMN
    #sample_time =  Column(DateTime , nullable=True, unique=True)


    # Explicit relationships with unambiguous foreign keys
    acquisition_time = relationship("DimTime", foreign_keys=[acquisition_time_id])
    instrument_time = relationship("DimTime", foreign_keys=[instrument_time_id])
    sample_time_f = relationship("DimTime", foreign_keys=[sample_time_id])

    platform = relationship("DimPlatform", foreign_keys=[platform_id])
    instrument = relationship("DimInstrument", foreign_keys=[instrument_id])
    parameter = relationship("DimParameter", foreign_keys=[parameter_id])
    unit = relationship("DimUnit", foreign_keys=[unit_id])
    acquisition_type = relationship("DimAcquisitionType", foreign_keys=[acquisition_type_id])

# Dimension Table for alarm level
class DimAlarmLevel(Base):
    __tablename__ = 'alarm_level'
    id = Column(Integer, primary_key=True)
    alarm_level = Column(String , nullable=False, unique=True)

# Dimension Table for alarm type
class DimAlarmType(Base):
    __tablename__ = 'alarm_type'
    id = Column(Integer, primary_key=True)
    alarm_type = Column(String , nullable=False, unique=True)

# Fact Table for instrument alarms  
class FactAlarm(Base):
    __tablename__ = 'alarm'
    id = Column(BigInteger, primary_key=True)
    measurement_id = Column(BigInteger, ForeignKey('measurement.id'), nullable=True)
    # foreign keys into dimension tables
    platform_id = Column(Integer, ForeignKey('platform.id'), nullable=False)
    instrument_id = Column(Integer, ForeignKey('instrument.id'), nullable=False)
    parameter_id = Column(Integer, ForeignKey('parameter.id'), nullable=True)

    # Foreign keys to the DimTime table
    sample_time_id = Column(BigInteger, ForeignKey('time.id'), nullable=False)

    #alarm-specific columns
    alarm_type_id = Column(Integer, ForeignKey('alarm_type.id'), nullable=False)
    alarm_level_id = Column(Integer, ForeignKey('alarm_level.id'), nullable=False)
    data_impacted = Column(Boolean, nullable=False)
    message = Column(String , nullable=False, unique=False)

    # Explicit relationships with unambiguous foreign keys
    sample_time = relationship("DimTime", foreign_keys=[sample_time_id])

    platform = relationship("DimPlatform", foreign_keys=[platform_id])
    instrument = relationship("DimInstrument", foreign_keys=[instrument_id])
    parameter = relationship("DimParameter", foreign_keys=[parameter_id])
    alarm_type = relationship("DimAlarmType", foreign_keys=[alarm_type_id])
    alarm_level = relationship("DimAlarmLevel", foreign_keys=[alarm_level_id])


 