---
title: 【读书笔记】《A Philosophy of Software Design》
date: 2025-01-10T21:07:27+08:00
tags:
- 读书笔记
- 软件设计
categories:
- 读书笔记
- 软件设计
description: 读万卷书
---

The most fundamental problem in computer science is **problem decomposition: how to take a complex problem and divide it up into pieces that can be solved independently.**

It's all about **complexity**.

## Complexity

Complexity is anything related to the structure of a software system that makes it hard to understand and modify the system.

Complexity manifests itself in three general ways:

1. **Change amplification**: a seemingly simple change requires code modifications in many different places.
   
2. **Cognitive load**: A higher cognitive load means that developers have to spend more time learning the required information.
   
3. **Unknown unknowns**: It is not obvious which pieces of code must be modified to complete a task, or what information a developer must have to carry out the task successfully. This is the worst kind of complexity.

Complexity is caused by two things: 

- **dependencies**:
- **obscurity**

So there are two general approaches to fighting complexity:

- **clean code**: Eliminating complexity by making code simpler and more obvious.
  
- **modular design**: A software system is divided up into modules, such as classes in an object-oriented language. The modules are designed to be relatively independent of each other, so that a programmer can work on one module without having to understand the details of other modules

### Strategic vs. Tactical Programming

Tactical programming means that your main focus is to get something working as soon as possible, such as a new feature or a bug fix, but it is short-sighted. It will make the system more complex in the future.

The first step towards becoming a good software designer is to realize that **working code isn’t enough.** Your primary goal must be to **produce a great design, which also happens to work.**

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/a-philosophy-of-sd-01.png)

## Modular Design

#### Different Layer, Different abstraction

Software systems are composed in layers, where higher layers use the facilities provided by lower layers. In a well-designed system, each layer provides a different abstraction from the layers above and below it; if you follow a single operation as it moves up and down through layers by invoking methods, the abstractions change with each method call.

**Pass-through methods**
If different layers have the same abstraction, such as pass-through methods or decorators, then there’s a good chance that they haven’t provided enough benefit to compensate for the additional infrastructure they represent.


There are several solutions for remove pass-through methods.

- Expose the lower level class directly to the callers of the high level class.
- Redistribute the functionality between the classes.
- Merge theme
![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/philo-software-design-02.png)

**Pass-through variable**
Another form of API duplication across layers is a pass-through variable, which is a variable that is passed down through a long chain of methods.

Pass-through variables add complexity, if a new variable comes into existence, you may have to modify a large number of interfaces and methods to pass the variable through all of the relevant paths.

You can use these methods for eliminating pass-though variables:

- Shared object
- Global variables
- Context object, this is better

![](https://pub-08b57ed9c8ce4fadab4077a9d577e857.r2.dev/philo-software-design-03.png)

**Decorators**

The decorator design pattern (also known as a “wrapper”) is one that encourages API duplication across layers. However, decorator classes tend to be shallow: they introduce a large amount of boilerplate for a small amount of new functionality.


You can consider alternatives before creating a decorator class:

- Add new functionality directly to the underlying class.
- If the new functionality is specialized for a particular use case, would it make sense to merge it with the use case, rather than creating a separate class?
- Merge the new functionality with an existing decorator.
- Could you implement it as a stand-alone class that is independent of the base class?


### Design general-purpose modules


Most modules have more users than developers, so it is better for the developers to suffer than the users. So it is more important for a module to have a simple interface than a simple implementation.

Pulling complexity down when:

- the complexity being pulled down is closely related to the class’s existing functionality.
- pulling the complexity down will result in simplifications elsewhere in the application
- pulling the complexity down simplifies the class’s interface. 





