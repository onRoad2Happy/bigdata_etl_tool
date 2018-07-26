#!/usr/bin/env python
#-*- encoding: utf-8 -*-
'''
Created on 2018年7月17日
@author: zuiweng.df
@summary: 使用sqoop etl工具
'''

import ConfigParser
import datetime
import os
import re
import traceback
import sys
import time
import subprocess
import random
import logging
from optparse import OptionParser


from com.xcom.dfupetl.model.DBTableInfo import ETLTable
from com.xcom.dfupetl.model.EtlMetadata import EtlDB, EtlTableTemplate, AppInfo
from com.xcom.dfupetl.utils.DBHelper import DBHelper

'''
sqoop表导入hive的工具
'''
class SqoopEtlTool(object):
    
    '''
       开始从mysql导入hive
    '''
    def startEtl(self):
        #创建日志路径
        today=datetime.date.today()
        formattedToday=today.strftime('%y%m%d')
        self.currPath=self.appInfo.etlLogPath+"/"+formattedToday+"/"+str(self.batchNumIn)
        os.system("rm -rf "+self.currPath)
        os.system("mkdir -p  "+self.currPath)
        

        self.realEtlTableList.sort(lambda a,b:b.torder-a.torder)
        self.splitTableDict={}
        
        if SqoopEtlTool.str2Bool(self.dropAllTable) :
            for k,tableTemplate in self.tableTemplateDict.items():
                ##EtlTableTemplate
                dbName=tableTemplate.dbName
                baseTableName="ods_"+dbName+"."+tableTemplate.tableName
        
                tempTableNameList=[baseTableName,baseTableName+"_daily_incr"]
                for tableName in tempTableNameList:
                    self.system(r''' hive -e  "  drop table IF  EXISTS  %s  " ''' % tableName,0) 
            
        
        #遍历循环所有的表
        ####ETLTable
        for tableInfo in self.realEtlTableList:
#                 dbName=tableInfo.dbName
#                 print dbName
                #如果是全量导入则创建表
                if  tableInfo.createTable==1 :
                    try:
                        self.exeCreateTable(tableInfo)
                    except Exception as e:
                        logging.error(r'exeCreateTable 出现问题: '+str(e))
                        traceback.print_exc()
                
                #全量导入数据
                if  tableInfo.etlAllData==1 : 
                    try:
                        self.extractAllData(tableInfo)
                    except Exception as e:
                        logging.error(r'exeSqoop 出现问题: '+str(e))
                        traceback.print_exc()
                    
                incrementCol=tableInfo.incrementCol
                useTimeInc=True
                if incrementCol is not None :
                    index=incrementCol.lower().find("id")
                    if index >= 0:
                        useTimeInc=False
                        
                if tableInfo.etlIncreamData==1:
                    if useTimeInc:
                        try:
                            self.extractIncrementData(tableInfo)
                            self.mergeTempData2RealTable(tableInfo)
                        except Exception as e:
                            logging.error(r'extractIncrementData or mergeTempData2RealTable 出现问题: '+str(e))
                            traceback.print_exc()
                    else:
                        self.insertEtlRes(tableInfo,1,0) 
                        
                
                currentPath=os.path.abspath(os.path.join(os.getcwd(), "."))
                os.system("rm -rf  %s/*.java" % currentPath)
                
        for keyName,tempTableInfo in self.splitTableDict.items():
            if tempTableInfo  is not None:
                targetDBName="ods_"+tempTableInfo.dbName+"."
                pkeyName=tempTableInfo.pkeyName
                increaseDataTable=targetDBName+tableInfo.targetTableName+"_daily_incr"
                allDataTable=targetDBName+tableInfo.targetTableName
                hiveTableDict={
                   "allDataTable":allDataTable,
                   "increaseDataTable":increaseDataTable,
                   "pkeyName":pkeyName
                }
                hiveCmd=r'''hive -e " insert overwrite    table {0[allDataTable]}    select * from ( select a.* from {0[allDataTable]} as a where a.{0[pkeyName]}  not in ( select  {0[pkeyName]} from {0[increaseDataTable]} union all select b.* from {0[increaseDataTable]} as b  ) tmp "  '''.format(hiveTableDict)
                logging.info( r"startEtl: hiveCmd %s" %  hiveCmd)
                self.system(hiveCmd)   
                self.insertEtlRes(tableInfo,3,0)      
                   
                    

    def system(self,cmd,sleepTime=1):
#         time.sleep(1)
        logging.warn(r"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! 执行如下命令： ")
        logging.info(cmd)
        if sleepTime >0:
            time.sleep(sleepTime)
            
        os.system(cmd)
#         cmdOut = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
#         while True:
#             line = cmdOut.stdout.readline()
#             print(line)
#             if subprocess.Popen.poll(cmdOut)==0:
#                 break 
                
                
    def mergeTempData2RealTable(self,tableInfo):
        ####ETLTable
        targetDBName="ods_"+tableInfo.dbName+"."
        allDataTable=targetDBName+tableInfo.targetTableName
        
        
        pkeyName=tableInfo.pkeyName
                
        
        hiveCmd=""
        #如果是多表则等所有的分表来导入到临时表之后，再导入真实表
        if tableInfo.isMutTable ==1 :
            keyName=allDataTable+":"+pkeyName
            self.splitTableDict[keyName]=tableInfo
            
            allDataTable=targetDBName+tableInfo.targetTableName+"_daily_incr"
            increaseDataTable=targetDBName+tableInfo.realTableName
            hiveTableDict={
               "allDataTable":allDataTable,
               "increaseDataTable":increaseDataTable,
               "pkeyName":pkeyName
            }
            hiveCmd=r'''hive -e " insert into    table {0[allDataTable]}    select * from ( select a.* from {0[allDataTable]} as a where a.{0[pkeyName]}  not in ( select  {0[pkeyName]} from {0[increaseDataTable]} ) union all select b.* from {0[increaseDataTable]} as b  ) tmp " '''.format(hiveTableDict)
        else:
            #单表则直接orverwrite
            increaseDataTable=targetDBName+tableInfo.targetTableName+"_daily_incr"
            hiveTableDict={
               "allDataTable":allDataTable,
               "increaseDataTable":increaseDataTable,
               "pkeyName":pkeyName
            }
            hiveCmd=r'''hive -e " insert overwrite    table {0[allDataTable]}    select * from ( select a.* from {0[allDataTable]} as a where a.{0[pkeyName]}  not in ( select  {0[pkeyName]} from {0[increaseDataTable]} ) union all select b.* from {0[increaseDataTable]} as b  ) tmp " '''.format(hiveTableDict)
          
        logging.info( r"mergeTempData2RealTable: hiveCmd %s" %  hiveCmd)
        self.system(hiveCmd)
        self.insertEtlRes(tableInfo,1,0) 
        
        
        
        
    
    '''
         向数据库中插入每一个etl table的记录
    '''
    def insertEtlRes(self,tableInfo,type,status):
        sourceTableName=tableInfo.realTableName
        targetTableName=tableInfo.targetTableName
        sourceDBName=tableInfo.dbName
        targetDBName="ods_"+tableInfo.dbName
        
        dataDict={
            "sourceTableName":sourceTableName,
            "targetTableName":targetTableName,
            "sourceDBName":sourceDBName,
            "targetDBName":targetDBName,
            "type":type,
            "batchNum":self.batchNumIn,
            "status":status
            }
        
        DBHelper.insert(self.configDBInfo,"table_exe_info",dataDict);
                    
    '''
    创建hive表
    '''
    def exeCreateTable(self,tableInfo):
        ####ETLTable
        dbName=tableInfo.dbName
        dbInfo=self.dbDict.get(dbName)
        sql="desc %s " % tableInfo.realTableName
        fetchResult=DBHelper.query(dbInfo,sql);
        rowcount=fetchResult[0]
        queryResult=fetchResult[1]
        baseTableName="ods_"+dbName+"."+tableInfo.targetTableName

        tempTableNameList=[baseTableName,baseTableName+"_daily_incr"]

              
        if (queryResult is not None) and rowcount>0 :
            for tableName in tempTableNameList:
                createTableStr=r''' hive -e  " create EXTERNAL table  IF NOT EXISTS  ''' +tableName+''' ( '''
                index=0
                maxSize=len(queryResult)
                for columnInfo in queryResult:
                    columnName=columnInfo[0]
                    columnType=columnInfo[1]
                    createTableStr=createTableStr+" "+columnName+" "
                    
                    #判断数据类型
                    if "int" in columnType:
                        columnType=" int "
                    elif "long" in columnType:
                        columnType=" bigint "
                    elif "varchar" in columnType:
                        columnType=" string "
                    elif "float" in columnType:
                        columnType=" float "
                    elif "double" in columnType:
                        columnType=" double "
                    elif "datetime" in columnType:
                        columnType=" timestamp "
                    elif "timestamp" in columnType:
                        columnType=" timestamp "
                    elif "text" in columnType:
                        columnType=" string "
                    elif "decimal" in columnType:
                        #使用数据库的原有配置旧ok
                        pass
                    
                    #是否是最后一行
                    if index < maxSize-1:
                        createTableStr=createTableStr+" "+columnType+" , "
                    else :
                        createTableStr=createTableStr+" "+columnType
                    index=index+1
                    
                   
                createTableStr=createTableStr+r''' ) ROW FORMAT DELIMITED FIELDS TERMINATED BY '\t'  STORED AS TEXTFILE "   '''
                logging.info( r"exeCreateTable: %s" % createTableStr)
                
                self.system(createTableStr)
                self.insertEtlRes(tableInfo,1,0) 
        
        
        
        
    '''
            全量导入数据
    '''
    def extractAllData(self,tableInfo):
        dbName=tableInfo.dbName
        dbInfo=self.dbDict.get(dbName)
        connStr=dbInfo.toConnString()
        
        self.insertEtlRes(tableInfo,2,0) 
        
        targetDir=self.appInfo.namenodeUrl+"/user/hive/tmp/warehouse/ods_"+dbName+".db/"+tableInfo.realTableName
        hadoopDbDict={
               "targetDir":targetDir
        }
        
        hdfsCmd=r'''hadoop  dfs -rm -r {0[targetDir]}  '''.format(hadoopDbDict)
        logging.info( r"extractAllData: hdfsCmd %s" %  hdfsCmd)
        self.system(hdfsCmd)
#         logFile=self.currPath+"/"+tableInfo.realTableName+"-hdfsCmd.txt"
#         fhandle = open(logFile, "w")  
#         subprocess.Popen(hdfsCmd, shell=True, stdout=fhandle).stdout  
#         fhandle.close()
        
        
        
        
        sqoopDbDict={
               "mysqlConn":connStr,
               "username":dbInfo.userName,
               "password":dbInfo.password,
               "tableName":tableInfo.realTableName,
               "mapperCount":tableInfo.mapperCount,
               "targetDir":targetDir,
               "pkeyName":tableInfo.pkeyName
            }
        
        sqoopCmd=r''' sqoop import    --connect {0[mysqlConn]}      --table {0[tableName]}    --username {0[username]}     --password {0[password]}  --split-by {0[pkeyName]}  --hive-drop-import-delims --null-string '\\N'     --null-non-string '\\N'   --target-dir {0[targetDir]}    --fields-terminated-by  '\t'     --lines-terminated-by '\n'  '''.format(sqoopDbDict)
        logging.info( r"extractAllData: sqoopCmd %s" %  sqoopCmd)
        self.system(sqoopCmd)
#         logFile=self.currPath+"/"+tableInfo.realTableName+"-sqoop.txt"
#         fhandle = open(logFile, "w")  
#         subprocess.Popen(sqoopCmd, shell=True, stdout=fhandle).stdout  
#         fhandle.close()
        
        
        tableName="ods_"+dbName+"."+tableInfo.targetTableName
        targetDir=self.appInfo.namenodeUrl+"/user/hive/tmp/warehouse/ods_"+dbName+".db/"+tableInfo.realTableName
        hiveDBDict={
               "tableName":tableName,
               "targetDir":targetDir
        }
        
        loadDataCmd=r''' hive -e "load data inpath '{0[targetDir]}' overwrite  into table {0[tableName]}  "   '''.format(hiveDBDict)
        logging.info( r"extractAllData: loadDataCmd %s" %  loadDataCmd)
        self.system(loadDataCmd)
#         logFile=self.currPath+"/"+tableName+"-hive.txt"
#         fhandle = open(logFile, "w")  
#         subprocess.Popen(sqoopCmd, shell=True, stdout=fhandle).stdout  
#         fhandle.close() 
          

    
    '''
          增量导入数据到临时表
    '''
    def extractIncrementData(self,tableInfo):
        dbName=tableInfo.dbName
        dbInfo=self.dbDict.get(dbName)
        connStr=dbInfo.toConnString()
        
        targetTableName=tableInfo.realTableName+"_daily_incr"
        
        targetDir=self.appInfo.namenodeUrl+"/user/hive/tmp/warehouse/ods_"+dbName+".db/"+targetTableName
        hadoopDbDict={
               "targetDir":targetDir
        }
        
        hdfsCmd=r'''hadoop  dfs -rm -r {0[targetDir]}  '''.format(hadoopDbDict)
        logging.info( r"extractIncrementData: hdfsCmd %s" %  hdfsCmd)
        self.system(hdfsCmd)
        
        
        now = datetime.datetime.now()
        zeroToday = now - datetime.timedelta(hours=now.hour, minutes=now.minute, seconds=now.second,microseconds=now.microsecond)
        lastToday = zeroToday - datetime.timedelta(hours=24, minutes=0, seconds=0)
        
        ####ETLTable
        whereSQL=" "
        
        #只支持时间啊，其他必错无疑
        if tableInfo.incrementType==1 :
            whereDict={
                   "incrementCol":tableInfo.incrementCol,
                   "zeroToday":zeroToday,
                   "lastToday":lastToday,
                }
            whereSQL='''  where {0[incrementCol]} > "{0[lastToday]}" and {0[incrementCol]} <  "{0[zeroToday]}"  and $CONDITIONS '''.format(whereDict)
        
        sqoopDbDict={
               "mysqlConn":connStr,
               "username":dbInfo.userName,
               "password":dbInfo.password,
               "tableName":tableInfo.realTableName,
               "mapperCount":tableInfo.mapperCount,
               "targetDir":targetDir,
               "pkeyName":tableInfo.pkeyName,
               "whereSQL":whereSQL
            }
        
        sqoopImportCmd=r''' sqoop import --connect {0[mysqlConn]} --username  {0[username]} --password {0[password]} --split-by {0[pkeyName]} --query 'select * from {0[tableName]}    {0[whereSQL]}'  --hive-drop-import-delims --null-string '\\N' --null-non-string '\\N' --target-dir {0[targetDir]}    --fields-terminated-by  '\t'     --lines-terminated-by '\n'  '''.format(sqoopDbDict)
        logging.info( r"extractIncrementData: sqoopImportCmd %s" %  sqoopImportCmd)
        self.system(sqoopImportCmd)
        
        targetTableName=tableInfo.targetTableName+"_daily_incr"
        tableName="ods_"+dbName+"."+targetTableName
        targetDir=self.appInfo.namenodeUrl+"/user/hive/tmp/warehouse/ods_"+dbName+".db/"+tableInfo.realTableName
        hiveDBDict={
               "tableName":tableName,
               "targetDir":targetDir
        }
        
        loadDataHiveCmd=r''' hive -e " load data inpath '{0[targetDir]}'   into table {0[tableName]}  "   '''.format(hiveDBDict)
        logging.info( r"extractIncrementData: loadDataHiveCmd %s" %  loadDataHiveCmd)
        self.system(loadDataHiveCmd)
        self.insertEtlRes(tableInfo,2,0) 
          
        
        
    
    def startFetchTables(self):
        logging.info( r"startFetch etl ......")
#         tablesStr=','.join(self.tableTemplateNameList);
        for dbName,dbInfo in self.dbDict.items():
            sql=" show tables "
            fetchResult=DBHelper.query(dbInfo,sql);
            if fetchResult  is  not None:
                rowcount=fetchResult[0]
                queryResult=fetchResult[1]
                
              
                if (queryResult is not None) and rowcount>0 :
                    queryResult=sorted(queryResult)
                    #遍历所有一个数据库中所有的表，查看表名是否符合我们所配置的表
                    for tinfo in queryResult:
                        realTableName=tinfo[0].lower()
                        isConfigTable=False
                        shortTableName=realTableName
                        #如果表明不是以数字结尾的
                        tableTemplate1=  self.tableTemplateDict.get(shortTableName) 
                        if (realTableName in self.tableTemplateNameList) and (tableTemplate1 is not None) and (tableTemplate1.isMutTable==0) :
                            isConfigTable=True
                        else :
                            rr=re.match(r"(.*?)_(\d+)",realTableName, re.M|re.I)
                            #如果表明不是以数字结尾的
                            if rr is not  None:
                                shortTableName=rr.group(1)
                                if shortTableName in self.tableTemplateNameList:
                                    isConfigTable=True
                                    
                        
                        #如果符合正则，说明是我们想要配置的表
                        if isConfigTable:
                            tableTemplate=  self.tableTemplateDict.get(shortTableName)  
                            try:
                                mytable=ETLTable(dbName,realTableName,tableTemplate)
                            except Exception as e:
                                traceback.print_exc()
                            self.realEtlTableList.append(mytable)
                
    @staticmethod            
    def str2Bool(str):
        return True if str.lower() == 'true' else False    
    
    
    
    
    def init(self,conf):
        '''
                     初始化配置参数
        '''
        logging.info( r"init etl ......")
        
        #放置数据库信息
        self.dbDict={}
        self.tableTemplateList=[]
        self.tableTemplateNameList=[]
        self.tableTemplateDict={}
        self.realEtlTableList=[]
        
        #存放所有的表字符串
        self.dbTableStrList={}
        
        self.dropAllTable=conf.get("default", "dropAllTable")
        
        connInfo=conf.get("default", "db.connInfo")
        infoList=connInfo.strip().split(":")
        configDBInfo=EtlDB(infoList[0],infoList[1],infoList[2],infoList[3],infoList[4])
        
        sql="select dbName,dbHost,dbPort,userName,password,enable  from etl_db where enable=1 "
        fetchResult=DBHelper.query(configDBInfo,sql);
        self.configDBInfo=configDBInfo
        
        if fetchResult is not None:
            rowncount=fetchResult[0]
            dbNameList=fetchResult[1]
            
            if rowncount>0 and dbNameList is not None:
                for dbrow in dbNameList:
                    dbName=dbrow[0]
                    dbHost=dbrow[1]
                    dbPort=dbrow[2]
                    userName=dbrow[3]
                    password=dbrow[4]
                    enable=dbrow[5]
                    dbInfo=EtlDB(dbName,dbHost,dbPort,userName,password,enable)
                    self.dbDict[dbName]=dbInfo
                    
        
        sql='''select a.id, a.tableName, a.isMutTable, a.mergeCol, a.incrementCol, 
        a.createTable, a.etlAllData, a.torder, a.mapperCount,a.pkeyName,a.incrementType,a.etlIncreamData,   b.dbName
               from etl_table_template  a  left join etl_db b 
               on a.dbId=b.id  where a.enable=1  
               order by a.torder desc , b.torder desc 
         '''
        fetchResult=DBHelper.query(configDBInfo,sql);
        
        if fetchResult is not None:
            rowncount=fetchResult[0]
            tableNameList=fetchResult[1]
            
            if rowncount>0 and tableNameList is not None:
                for dbrow in tableNameList:
                    ids=dbrow[0]
                    tableName=dbrow[1]
                    isMutTable=dbrow[2]
                    mergeCol=dbrow[3]
                    incrementCol=dbrow[4]
                    createTable=dbrow[5]
                    etlAllData=dbrow[6]
                    torder=int(dbrow[7])
                    mapperCount=int(dbrow[8])
                    pkeyName=dbrow[9]
                    incrementType=dbrow[10]
                    etlIncreamData=int(dbrow[11])
                    dbName=dbrow[12]
                    self.tableTemplateNameList.append(tableName)
                    
                    tempTable=EtlTableTemplate(ids,tableName,dbName,isMutTable,mergeCol,incrementCol,createTable,etlAllData,torder,pkeyName,incrementType,etlIncreamData,mapperCount)
                    self.tableTemplateDict[tableName]=tempTable
                    
        
        envName=conf.get("default", "envName")
        if envName not in "dev,test,production":
            envName="dev"
        logging.info( r"当前环境为:  %s" % envName)
        sql="select id,etlLogPath,newDataTempDir,namenodeUrl   from app_config  where envName='%s' limit 1 "  % envName
        fetchResult=DBHelper.query(configDBInfo,sql);
        
        if fetchResult is not None:
            rowncount=fetchResult[0]
            dbNameList=fetchResult[1]
            
            if rowncount>0 and dbNameList is not None:
                for dbrow in dbNameList:
                    ids=dbrow[0]
                    etlLogPath=dbrow[1]
                    newDataTempDir=dbrow[2]
                    namenodeUrl=dbrow[3]
    
                    appInfo=AppInfo(ids,etlLogPath,newDataTempDir,namenodeUrl)
                    self.appInfo=appInfo
        
        now=datetime.datetime.now()
        dataDict={
            "gmt_create":now,
            "gmt_modify":now
            }
        DBHelper.insert(configDBInfo,"exe_batch_info",dataDict);
        batchNumIn=random.randint(100000,900000)
        fetchResult=fetchResult=DBHelper.query(configDBInfo,"select max(batchNum) from exe_batch_info");
        if  fetchResult is not None:
            rowncount=fetchResult[0]
            batchNumList=fetchResult[1]
            
            if rowncount>0 and batchNumList is not None:
                for dbrow in batchNumList:
                    batchNumIn=int(dbrow[0])
        
        self.batchNumIn=batchNumIn
        
        logging.info( r"init db finish ......")
    
    def endFetch(self):
        currentPath=os.path.abspath(os.path.join(os.getcwd(), "."))
        os.system("rm -rf  %s/*.java" % currentPath)
        logging.info( r"endFetch etl ......")
        logging.info( r"$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$")




if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(filename)s[line:%(lineno)d] - %(levelname)s: %(message)s')
    currentPath=os.path.abspath(os.path.join(os.getcwd(), "."))
    os.system("rm -rf  %s/*.java" % currentPath)
    parser = OptionParser(usage="%prog -f server.list -u root ...  versrion 1",version="%prog 1")
    parser.add_option("-e", "--etlType",action="store",dest="etlType",help="etlType: all数据 全量导入 , increment 增量导入。默认值为全量导入",default="all")
    parser.add_option("-t", "--tables",action="store", dest="tables",help="操作的数据表名列表使用,符号分开，比如table1,table2,table3。默认值为空，即所有表操作",default="")
    (options, args) = parser.parse_args()
    
    sys.path.append(currentPath)
    conFile="./conf/app.conf"
    conf = ConfigParser.SafeConfigParser()
    conf.read(conFile)
    etlPathStr=conf.get("default", "etlToolEnv.path")
    libPathStr=conf.get("default", "etlTool.lib")
    cdhHadoopHome=conf.get("default", "cdhHadoop.home")
    
    mypath=os.path.abspath(os.path.join(os.getcwd(), "./com"))
    sys.path.append(mypath)
    mypath=os.path.abspath(os.path.join(os.getcwd(), "./conf"))
    sys.path.append(mypath)
    
    ##将各种环境path追加进入python环境
    etlPathList=etlPathStr.split(";")
    libPathList=libPathStr.split(";")
    etlPathList.extend(libPathList)
    
    
    for path in etlPathList:
        path="%s/%s" % (cdhHadoopHome,path.strip())
        if path is not None:
            sys.path.append(path)
            print  path
    

    
    reload(sys)     
    sys.setdefaultencoding('utf-8')
    etl=SqoopEtlTool()
    etl.init(conf)
    etl.startFetchTables()
    etl.startEtl()
    etl.endFetch()
